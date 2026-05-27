"""
Sistema de comandas para meseros.

Flujo:
  Mesero  → /pedido Mesa 3 | 2 almuerzos + 1 extra pollo
  Bot     → confirma al mesero + notifica a cocina y supervisora
  Cocina  → ve la lista con /pedidos
  Cocina  → /listo 5  cuando el pedido #5 está listo
  Bot     → avisa al mesero: "¡Corre a buscar el pedido #5!"
  Mesero  → /entregado 5  cuando lo lleva a la mesa
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
import database as db
import config
from handlers.roles import any_role, require_role, rest_label

logger = logging.getLogger(__name__)

_STATUS_ICON = {
    "pending": "⏳",
    "ready":   "🔔",
    "served":  "✅",
}
_STATUS_LABEL = {
    "pending": "En cocina",
    "ready":   "¡LISTO — ir a buscar!",
    "served":  "Entregado",
}


# ── /pedido ──────────────────────────────────────────────────────────────────

@require_role("mesero", "cashier", "supervisor", "boss")
async def cmd_pedido(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /pedido Mesa 3 | 2 almuerzos + 1 extra pollo
    /pedido 1 almuerzo + limonada        ← sin mesa también funciona
    """
    rid        = ctx.user_data["restaurant_id"]
    rname      = ctx.user_data["restaurant_name"]
    mesero_id  = str(update.effective_user.id)
    mesero_name = ctx.user_data.get("username") or update.effective_user.full_name

    if not rid:
        await update.message.reply_text(
            "👑 Especifica el restaurante:\n`/pedido oasis Mesa 3 | 2 almuerzos`",
            parse_mode="Markdown"
        )
        return

    args = " ".join(ctx.args) if ctx.args else ""
    if not args.strip():
        await update.message.reply_text(
            "📋 *Formato:*\n"
            "`/pedido Mesa 3 | 2 almuerzos + 1 extra pollo`\n\n"
            "Sin mesa: `/pedido 2 almuerzos + limonada`",
            parse_mode="Markdown"
        )
        return

    # Parsear mesa e ítems
    if "|" in args:
        parts     = [p.strip() for p in args.split("|", 1)]
        table_ref = parts[0]
        items     = parts[1] if len(parts) > 1 and parts[1] else args.strip()
    else:
        table_ref = ""
        items     = args.strip()

    order_id = db.create_order(rid, mesero_id, mesero_name, table_ref, items)

    table_line = f"🪑 Mesa: *{table_ref}*\n" if table_ref else "🪑 Sin mesa asignada\n"

    # Confirmación al mesero
    await update.message.reply_text(
        f"✅ *Pedido #{order_id} registrado — {rest_label(rname)}*\n\n"
        f"{table_line}"
        f"🍽 {items}\n\n"
        f"_La cocina fue notificada. Te avisaremos cuando esté listo._",
        parse_mode="Markdown"
    )

    # Notificación a cocina y supervisora
    notify_msg = (
        f"🆕 *Nuevo pedido #{order_id} — {rest_label(rname)}*\n\n"
        f"{table_line}"
        f"🍽 *{items}*\n"
        f"👤 Mesero: {mesero_name}\n"
        f"🕐 {db.today()}\n\n"
        f"Cuando esté listo: `/listo {order_id}`"
    )
    recipients = (
        config.OASIS_CHIEF_IDS | config.OASIS_SUPERVISOR_IDS
        if rname == "oasis"
        else config.DALI_CHIEF_IDS | config.DALI_SUPERVISOR_IDS
    ) | config.ADMIN_IDS

    for tid in recipients:
        try:
            await ctx.bot.send_message(chat_id=tid, text=notify_msg, parse_mode="Markdown")
        except Exception:
            pass


# ── /pedidos — vista de cocina / supervisora ─────────────────────────────────

@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_pedidos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lista de todos los pedidos de hoy para cocina / supervisora."""
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    role  = ctx.user_data["role"]

    # Boss sin restaurante → ambos
    if role == "boss" and not rid:
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            msgs.append(_build_pedidos_list(rest["id"], name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    await update.message.reply_text(_build_pedidos_list(rid, rname), parse_mode="Markdown")


def _build_pedidos_list(rid: int, rname: str) -> str:
    orders = db.get_orders_today(rid)
    if not orders:
        return f"{rest_label(rname)}\n📋 Sin pedidos registrados hoy."

    pending = [o for o in orders if o["status"] == "pending"]
    ready   = [o for o in orders if o["status"] == "ready"]
    served  = [o for o in orders if o["status"] == "served"]

    lines = [f"🍽 *Pedidos de hoy — {rest_label(rname)}*\n"]

    if pending:
        lines.append(f"⏳ *EN COCINA ({len(pending)}):*")
        for o in pending:
            t = o["created_at"][11:16]
            mesa = f"Mesa {o['table_ref']}" if o["table_ref"] else "Sin mesa"
            lines.append(f"  📋 *#{o['id']}* | {t} | {mesa}")
            lines.append(f"     {o['items']}")
            lines.append(f"     👤 _{o['mesero_name']}_")
        lines.append("")

    if ready:
        lines.append(f"🔔 *LISTOS — SIN ENTREGAR ({len(ready)}):*")
        for o in ready:
            t = o["ready_at"][11:16] if o["ready_at"] else "—"
            mesa = f"Mesa {o['table_ref']}" if o["table_ref"] else "Sin mesa"
            lines.append(f"  ✅ *#{o['id']}* | Listo {t} | {mesa}")
            lines.append(f"     {o['items']}")
        lines.append("")

    if served:
        lines.append(f"✅ *ENTREGADOS HOY ({len(served)}):*")
        for o in served:
            mesa = f"Mesa {o['table_ref']}" if o["table_ref"] else "Sin mesa"
            lines.append(f"  ☑ #{o['id']} {mesa} — {o['mesero_name']}")

    if pending:
        ids = " · ".join(f"/listo {o['id']}" for o in pending[:5])
        lines.append(f"\nMarcar listo: {ids}")

    return "\n".join(lines)


# ── /listo — cocina marca pedido como listo ───────────────────────────────────

@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_listo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /listo 5 — marca el pedido #5 como listo y avisa al mesero
    """
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    user  = ctx.user_data.get("username") or update.effective_user.full_name

    if not ctx.args:
        await update.message.reply_text(
            "📋 Uso: `/listo <número de pedido>`\nEjemplo: `/listo 5`",
            parse_mode="Markdown"
        )
        return

    try:
        order_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Indica el número del pedido. Ej: `/listo 5`",
                                        parse_mode="Markdown")
        return

    order = db.get_order_by_id(order_id)
    if not order:
        await update.message.reply_text(f"❌ No existe el pedido #{order_id}.")
        return

    if order["status"] != "pending":
        icon = _STATUS_ICON.get(order["status"], "—")
        label = _STATUS_LABEL.get(order["status"], order["status"])
        await update.message.reply_text(
            f"⚠️ El pedido #{order_id} ya está en estado: {icon} *{label}*",
            parse_mode="Markdown"
        )
        return

    ok = db.mark_order_ready(order_id)
    if not ok:
        await update.message.reply_text("❌ No se pudo actualizar el pedido.")
        return

    mesa = f"Mesa {order['table_ref']}" if order["table_ref"] else "Sin mesa"

    # Confirmación a la cocina
    await update.message.reply_text(
        f"✅ Pedido *#{order_id}* marcado como listo\n"
        f"🪑 {mesa} — 👤 {order['mesero_name']}\n"
        f"_El mesero fue notificado._",
        parse_mode="Markdown"
    )

    # Aviso al mesero — urgente, que corra a buscarlo
    mesero_msg = (
        f"🔔 *¡PEDIDO #{order_id} LISTO!* — {rest_label(rname)}\n\n"
        f"🪑 {mesa}\n"
        f"🍽 {order['items']}\n\n"
        f"👨‍🍳 Preparado por: {user}\n\n"
        f"*¡Ve a buscar el pedido ahora!* 🏃\n"
        f"Cuando lo entregues: `/entregado {order_id}`"
    )
    try:
        await ctx.bot.send_message(
            chat_id=order["mesero_id"],
            text=mesero_msg,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo notificar al mesero {order['mesero_id']}: {e}")


# ── /mis_pedidos — historial del mesero ──────────────────────────────────────

@any_role
async def cmd_mis_pedidos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """El mesero ve todos sus pedidos del día."""
    rid        = ctx.user_data["restaurant_id"]
    rname      = ctx.user_data["restaurant_name"]
    mesero_id  = str(update.effective_user.id)

    if not rid:
        await update.message.reply_text(
            "Primero dile al bot en qué restaurante estás:\n"
            "`/mi_restaurante oasis` o `/mi_restaurante dali`",
            parse_mode="Markdown"
        )
        return

    orders = db.get_orders_by_mesero_today(rid, mesero_id)

    if not orders:
        await update.message.reply_text(
            f"{rest_label(rname)}\n📋 No tienes pedidos registrados hoy.\n\n"
            f"Para registrar: `/pedido Mesa 3 | 2 almuerzos`",
            parse_mode="Markdown"
        )
        return

    # Agrupar por mesa (orden numérico natural)
    by_table: dict = {}
    sin_mesa = []
    for o in orders:
        if o["table_ref"]:
            by_table.setdefault(o["table_ref"], []).append(o)
        else:
            sin_mesa.append(o)

    def _sk(t: str):
        try:
            return (0, int(t))
        except ValueError:
            return (1, t.lower())

    lines = [f"📋 *Mis pedidos hoy — {rest_label(rname)}*\n"]
    ready_ids = []

    def _add_order(o):
        icon  = _STATUS_ICON.get(o["status"], "—")
        label = _STATUS_LABEL.get(o["status"], o["status"])
        t     = o["created_at"][11:16]
        lines.append(f"  {icon} *#{o['id']}* — {t}")
        lines.append(f"     {o['items']}")
        lines.append(f"     _{label}_")
        if o["status"] == "ready":
            ready_ids.append(o["id"])

    for mesa in sorted(by_table.keys(), key=_sk):
        lines.append(f"🪑 *Mesa {mesa}*")
        for o in by_table[mesa]:
            _add_order(o)
        lines.append("")

    if sin_mesa:
        lines.append("🪑 *Sin mesa*")
        for o in sin_mesa:
            _add_order(o)
        lines.append("")

    if ready_ids:
        lines.append("🔔 *¡Tienes pedidos listos para recoger!*")
        for oid in ready_ids:
            lines.append(f"  → `/entregado {oid}` cuando lo lleves a la mesa")

    await update.message.reply_text("\n".join(lines).rstrip(), parse_mode="Markdown")


# ── /entregado — mesero confirma entrega al cliente ──────────────────────────

@any_role
async def cmd_entregado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /entregado 5 — el mesero confirma que entregó el pedido #5 al cliente
    """
    mesero_id = str(update.effective_user.id)
    rname     = ctx.user_data["restaurant_name"]

    if not ctx.args:
        await update.message.reply_text(
            "📋 Uso: `/entregado <número de pedido>`\nEjemplo: `/entregado 5`",
            parse_mode="Markdown"
        )
        return

    try:
        order_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Indica el número del pedido.",
                                        parse_mode="Markdown")
        return

    order = db.get_order_by_id(order_id)
    if not order:
        await update.message.reply_text(f"❌ No existe el pedido #{order_id}.")
        return

    if order["mesero_id"] != mesero_id:
        await update.message.reply_text(
            "⛔ Solo puedes marcar tus propios pedidos como entregados."
        )
        return

    ok = db.mark_order_served(order_id, mesero_id)
    if not ok:
        status = order["status"]
        if status == "served":
            await update.message.reply_text(f"✅ El pedido #{order_id} ya estaba marcado como entregado.")
        else:
            await update.message.reply_text(f"⚠️ No se pudo marcar como entregado (estado: {status}).")
        return

    mesa = f"Mesa {order['table_ref']}" if order["table_ref"] else "Sin mesa"
    await update.message.reply_text(
        f"✅ *Pedido #{order_id} entregado*\n"
        f"🪑 {mesa}\n"
        f"🍽 {order['items']}\n\n"
        f"¡Buen servicio! 👏",
        parse_mode="Markdown"
    )
