from telegram import Update
from telegram.ext import ContextTypes
import database as db
import config
from handlers.roles import any_role, require_role, rest_label


@any_role
async def cmd_faltantes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra faltantes de HOY (pendientes)."""
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            items = db.get_all_shortages_today(rest["id"])
            pending = [i for i in items if i["status"] == "pending"]
            msgs.append(_format_shortages(pending, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    rid = ctx.user_data["restaurant_id"]
    items = db.get_all_shortages_today(rid)
    pending = [i for i in items if i["status"] == "pending"]
    await update.message.reply_text(_format_shortages(pending, rname), parse_mode="Markdown")


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
    También acepta sin separador: /agregar_faltante Tomates
    Ejemplo: /agregar_faltante Tomates | 5 kg
    """
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    user  = ctx.user_data.get("username") or update.effective_user.full_name
    args  = " ".join(ctx.args) if ctx.args else ""

    if not args.strip():
        await update.message.reply_text(
            "📋 *Formato:*\n`/agregar_faltante Ítem | Cantidad`\n\n"
            "Ejemplo: `/agregar_faltante Tomates | 5 kg`\n"
            "Sin cantidad: `/agregar_faltante Tomates`",
            parse_mode="Markdown"
        )
        return

    if "|" in args:
        parts = [p.strip() for p in args.split("|", 1)]
        item_name = parts[0]
        quantity  = parts[1] if len(parts) > 1 and parts[1] else "ver"
    else:
        # No pipe: entire text is item name, quantity unspecified
        item_name = args.strip()
        quantity  = "ver"

    if not item_name:
        await update.message.reply_text(
            "📋 *Formato:*\n`/agregar_faltante Ítem | Cantidad`\n\n"
            "Ejemplo: `/agregar_faltante Tomates | 5 kg`",
            parse_mode="Markdown"
        )
        return

    db.add_shortage(rid, item_name, quantity, user)
    await update.message.reply_text(
        f"✅ Agregado a faltantes de {rest_label(rname)}:\n"
        f"🛒 *{item_name}* — {quantity}",
        parse_mode="Markdown"
    )

    # Notificar a supervisores (no si el que agregó ya es supervisor o boss)
    role = ctx.user_data.get("role", "")
    if role == "kitchen_chief":
        notify_ids = (
            config.OASIS_SUPERVISOR_IDS if rname == "oasis" else config.DALI_SUPERVISOR_IDS
        )
        notify_msg = (
            f"📋 *Nuevo faltante registrado — {rest_label(rname)}*\n\n"
            f"🛒 *{item_name}* — {quantity}\n"
            f"👤 Registrado por: {user}\n\n"
            f"Ver lista: /faltantes"
        )
        for tid in notify_ids:
            try:
                await ctx.bot.send_message(chat_id=tid, text=notify_msg, parse_mode="Markdown")
            except Exception:
                pass


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
    """Planilla de cierre de turno: muestra todo lo de HOY (pendiente + comprado)."""
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    today = db.today()

    all_today = db.get_all_shortages_today(rid)
    pending = [i for i in all_today if i["status"] == "pending"]
    bought  = [i for i in all_today if i["status"] == "bought"]

    lines = [f"📋 *Planilla cierre de turno — {rest_label(rname)}*",
             f"📅 {today}\n"]

    if pending:
        lines.append(f"🔴 *Pendiente de comprar ({len(pending)}):*")
        for item in pending:
            lines.append(f"  ☐ {item['item_name']} — {item['quantity_needed']}")
            lines.append(f"     _Registrado por {item['updated_by']}_")

    if bought:
        lines.append(f"\n🟢 *Ya comprado hoy ({len(bought)}):*")
        for item in bought:
            lines.append(f"  ☑ ~~{item['item_name']}~~")

    if not pending and not bought:
        lines.append("✅ Sin faltantes registrados hoy.\nUsa /stock\\_ok para confirmar stock.")

    if pending:
        lines.append(f"\n⏳ Quedan {len(pending)} pendiente(s).")
        lines.append("Usa /stock\\_ok cuando todo esté comprado.")
    else:
        lines.append("\n✅ Todo comprado. Usa /stock\\_ok para confirmar.")

    lines.append("\n_/agregar\\_faltante Ítem | Cantidad_")
    lines.append("_/marcar\\_comprado Ítem_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@require_role("kitchen_chief", "boss")
async def cmd_stock_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Confirma que el stock del día está completo."""
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    user  = ctx.user_data.get("username") or update.effective_user.full_name

    # Solo mira pendientes de HOY
    all_today = db.get_all_shortages_today(rid)
    pending   = [i for i in all_today if i["status"] == "pending"]

    if pending:
        items_str = "\n".join(f"  • {i['item_name']} — {i['quantity_needed']}" for i in pending)
        await update.message.reply_text(
            f"⚠️ Aún hay *{len(pending)}* ítem(s) pendiente(s) en {rest_label(rname)}:\n\n"
            f"{items_str}\n\n"
            f"Marca cada uno con `/marcar_comprado Ítem` cuando lo compren.\n"
            f"O usa `/stock_ok` de nuevo cuando estén todos.",
            parse_mode="Markdown"
        )
        return

    bought = [i for i in all_today if i["status"] == "bought"]
    resumen = ""
    if bought:
        resumen = "\n📦 Comprado hoy:\n" + "\n".join(f"  ✅ {i['item_name']}" for i in bought)

    await update.message.reply_text(
        f"✅ *Stock OK* — {rest_label(rname)}\n"
        f"Confirmado por: {user}\n"
        f"📅 {db.today()}"
        f"{resumen}\n\n"
        f"¡Todo listo para mañana! 🎉",
        parse_mode="Markdown"
    )
