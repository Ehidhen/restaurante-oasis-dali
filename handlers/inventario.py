from telegram import Update
from telegram.ext import ContextTypes
import database as db
from handlers.roles import any_role, require_role, rest_label


@any_role
async def cmd_faltantes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            items = db.get_shortages(rest["id"])
            msgs.append(_format_shortages(items, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    rid = ctx.user_data["restaurant_id"]
    items = db.get_shortages(rid)
    await update.message.reply_text(_format_shortages(items, rname), parse_mode="Markdown")


def _format_shortages(items: list, rname: str) -> str:
    label = rest_label(rname)
    if not items:
        return f"{label}\n✅ No hay faltantes pendientes."
    lines = [f"{label} — Lista de faltantes\n"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. 🛒 {item['item_name']} — {item['quantity_needed']}")
    return "\n".join(lines)


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_agregar_faltante(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Uso: /agregar_faltante <ítem> | <cantidad>
    Ejemplo: /agregar_faltante Tomates | 5 kg
    """
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    args = " ".join(ctx.args) if ctx.args else ""
    parts = [p.strip() for p in args.split("|")]

    if len(parts) < 2 or not parts[0]:
        await update.message.reply_text(
            "📋 *Formato:*\n`/agregar_faltante Ítem | Cantidad`\n\n"
            "Ejemplo: `/agregar_faltante Tomates | 5 kg`",
            parse_mode="Markdown"
        )
        return

    item_name = parts[0]
    quantity = parts[1] if len(parts) > 1 else "1"

    db.add_shortage(rid, item_name, quantity)
    await update.message.reply_text(
        f"✅ Agregado a faltantes de {rest_label(rname)}:\n"
        f"🛒 *{item_name}* — {quantity}",
        parse_mode="Markdown"
    )


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_marcar_comprado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Uso: /marcar_comprado tomates"""
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    args = " ".join(ctx.args) if ctx.args else ""

    if not args.strip():
        await update.message.reply_text(
            "📋 Uso: `/marcar_comprado <nombre del ítem>`",
            parse_mode="Markdown"
        )
        return

    ok = db.mark_shortage_bought(rid, args.strip())
    if ok:
        await update.message.reply_text(
            f"✅ Marcado como comprado en {rest_label(rname)}: *{args.strip()}*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ No encontré ese ítem pendiente en {rest_label(rname)}.\n"
            f"Verifica con /faltantes"
        )


@require_role("kitchen_chief", "boss")
async def cmd_checklist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    pending = db.get_shortages(rid, "pending")
    bought = db.get_shortages(rid, "bought")

    lines = [f"📋 *Checklist fin de turno — {rest_label(rname)}*\n"]

    if pending:
        lines.append("🔴 *Pendientes de comprar:*")
        for item in pending:
            lines.append(f"  ☐ {item['item_name']} — {item['quantity_needed']}")

    if bought:
        lines.append("\n🟢 *Ya comprado hoy:*")
        for item in bought:
            lines.append(f"  ☑ {item['item_name']}")

    if not pending and not bought:
        lines.append("✅ Sin faltantes registrados. ¿Todo completo?\nUsa /stock_ok para confirmar.")

    lines.append("\nUsa /agregar_faltante para agregar ítems.")
    lines.append("Usa /stock_ok cuando todo esté completo.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@require_role("kitchen_chief", "boss")
async def cmd_stock_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    pending = db.get_shortages(rid, "pending")
    if pending:
        items_str = "\n".join(f"• {i['item_name']}" for i in pending)
        await update.message.reply_text(
            f"⚠️ Aún hay {len(pending)} ítems pendientes en {rest_label(rname)}:\n\n"
            f"{items_str}\n\n"
            f"Usa /marcar_comprado <ítem> para marcarlos o agréga nuevos con /agregar_faltante.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"✅ *Stock confirmado* en {rest_label(rname)}.\n"
        f"Todo en orden para mañana. ¡Buen trabajo!",
        parse_mode="Markdown"
    )
