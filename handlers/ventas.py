from telegram import Update
from telegram.ext import ContextTypes, Application
import database as db
import config
from handlers.roles import any_role, require_role, rest_label

LOW_THRESHOLD = config.ALERT_LOW_THRESHOLD


async def _send_alert(app: Application, restaurant_id: int, restaurant_name: str, qty: int):
    """Send low-stock or zero-stock alert to all staff of the restaurant."""
    if qty == 0:
        msg = (
            f"🚨 *ALERTA URGENTE — {rest_label(restaurant_name).upper()}*\n\n"
            f"⛔ Se agotaron todos los almuerzos.\n"
            f"El cajero ya no puede registrar ventas.\n"
            f"Considera solicitar una transferencia con /transferir"
        )
    else:
        msg = (
            f"⚠️ *ALERTA — {rest_label(restaurant_name)}*\n\n"
            f"Quedan solo *{qty} almuerzos*.\n"
            f"Avisa al jefe de cocina."
        )

    ids_to_notify = config.all_ids_for_restaurant(restaurant_name) | config.ADMIN_IDS
    for tid in ids_to_notify:
        try:
            await app.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
        except Exception:
            pass


async def _check_and_alert(app: Application, restaurant_id: int, restaurant_name: str, qty: int):
    if qty == 0 or qty == LOW_THRESHOLD:
        await _send_alert(app, restaurant_id, restaurant_name, qty)


@any_role
async def cmd_quedan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        lines = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            qty = db.get_current_qty(rest["id"])
            bar = _qty_bar(qty)
            lines.append(f"{rest_label(name)}: *{qty}* almuerzos {bar}")
        await update.message.reply_text(
            "🔢 *Almuerzos disponibles ahora mismo*\n\n" + "\n".join(lines),
            parse_mode="Markdown"
        )
        return

    rid = ctx.user_data["restaurant_id"]
    qty = db.get_current_qty(rid)
    bar = _qty_bar(qty)
    estado = "❌ AGOTADO" if qty == 0 else ("⚠️ Pocas unidades" if qty <= LOW_THRESHOLD else "✅ OK")
    await update.message.reply_text(
        f"{rest_label(rname)}\n"
        f"🔢 Almuerzos disponibles: *{qty}* {bar}\n"
        f"Estado: {estado}",
        parse_mode="Markdown"
    )


def _qty_bar(qty: int) -> str:
    if qty == 0:
        return "🟥🟥🟥🟥🟥"
    if qty <= 5:
        filled = min(qty, 5)
        return "🟧" * filled + "⬜" * (5 - filled)
    if qty <= 20:
        return "🟨🟨🟨🟨🟨"
    return "🟩🟩🟩🟩🟩"


@require_role("cashier", "kitchen_chief", "supervisor", "boss")
async def cmd_venta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    uid = str(update.effective_user.id)

    # Parse quantity
    n = 1
    if ctx.args:
        try:
            n = int(ctx.args[0])
            if n < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Indica un número válido. Ej: `/venta 3`",
                                            parse_mode="Markdown")
            return

    qty = db.get_current_qty(rid)
    if qty == 0:
        await update.message.reply_text(
            f"⛔ No hay almuerzos disponibles en {rest_label(rname)}.\n"
            f"No se puede registrar la venta."
        )
        return

    if qty < n:
        await update.message.reply_text(
            f"⚠️ Solo quedan *{qty}* almuerzos. No puedes vender {n}.",
            parse_mode="Markdown"
        )
        return

    menu = db.get_menu(rid)
    price = menu["price"] if menu else 0.0
    amount = price * n

    db.adjust_qty(rid, -n)
    db.register_sale(rid, "almuerzo", n, amount, uid)

    new_qty = db.get_current_qty(rid)
    bar = _qty_bar(new_qty)

    msg = (
        f"✅ Venta registrada — {rest_label(rname)}\n"
        f"🍽 {n} almuerzo(s) × ${price:.2f} = *${amount:.2f}*\n"
        f"🔢 Quedan: *{new_qty}* {bar}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

    await _check_and_alert(ctx.application, rid, rname, new_qty)


@require_role("kitchen_chief", "boss")
async def cmd_ajustar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Uso: /ajustar 45  — corrige manualmente el contador."""
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    if not ctx.args:
        qty = db.get_current_qty(rid)
        await update.message.reply_text(
            f"🔢 Cantidad actual: *{qty}*\n"
            f"Uso: `/ajustar <nueva_cantidad>`",
            parse_mode="Markdown"
        )
        return

    try:
        new_qty = int(ctx.args[0])
        if new_qty < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Indica un número entero positivo.")
        return

    db.set_qty(rid, new_qty)
    await update.message.reply_text(
        f"✅ Contador ajustado en {rest_label(rname)}: *{new_qty}* almuerzos",
        parse_mode="Markdown"
    )
    await _check_and_alert(ctx.application, rid, rname, new_qty)


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_sin_almuerzos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    db.set_qty(rid, 0)
    await update.message.reply_text(
        f"⛔ Marcado como *SIN ALMUERZOS* en {rest_label(rname)}.\n"
        f"Notificando a todo el equipo…",
        parse_mode="Markdown"
    )
    await _send_alert(ctx.application, rid, rname, 0)

    # Check if other restaurant has surplus
    other_rid = db.other_restaurant_id(rid)
    other_rest = db.get_restaurant_by_id(other_rid)
    other_qty = db.get_current_qty(other_rid)
    if other_qty > 10:
        suggestion = (
            f"💡 *Sugerencia automática*\n"
            f"{rest_label(other_rest['name'])} tiene *{other_qty}* almuerzos disponibles.\n"
            f"¿Solicitar una transferencia?\nUsa: `/transferir <cantidad>`"
        )
        for tid in config.all_ids_for_restaurant(rname) | config.all_ids_for_restaurant(other_rest["name"]) | config.ADMIN_IDS:
            try:
                await ctx.application.bot.send_message(
                    chat_id=tid, text=suggestion, parse_mode="Markdown"
                )
            except Exception:
                pass
