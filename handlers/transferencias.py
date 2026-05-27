from telegram import Update
from telegram.ext import ContextTypes
import database as db
import config
from handlers.roles import require_role, rest_label


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_transferir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Solicita N almuerzos del otro restaurante.
    Uso: /transferir <cantidad>
    """
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    uid = str(update.effective_user.id)

    if not ctx.args:
        await update.message.reply_text(
            "📋 Uso: `/transferir <cantidad>`\n"
            "Ejemplo: `/transferir 10`",
            parse_mode="Markdown"
        )
        return

    try:
        qty = int(ctx.args[0])
        if qty < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Indica un número entero positivo.")
        return

    # Check for an already-active transfer between both restaurants
    existing = db.get_pending_transfer(rid)
    if existing and existing["status"] in ("requested", "sent"):
        status_emoji = "📦" if existing["status"] == "sent" else "⏳"
        await update.message.reply_text(
            f"⚠️ Ya hay una transferencia activa (#{existing['id']}).\n"
            f"{status_emoji} Estado: *{existing['status']}*\n\n"
            f"Espera a que se complete antes de solicitar otra.\n"
            f"Usa `/confirmar_envio` o `/confirmar_llegada` para avanzarla.",
            parse_mode="Markdown"
        )
        return

    other_rid = db.other_restaurant_id(rid)
    other_rest = db.get_restaurant_by_id(other_rid)
    other_qty = db.get_current_qty(other_rid)

    if other_qty < qty:
        await update.message.reply_text(
            f"⚠️ {rest_label(other_rest['name'])} solo tiene *{other_qty}* almuerzos.\n"
            f"No puede enviar {qty}.",
            parse_mode="Markdown"
        )
        return

    transfer_id = db.create_transfer(other_rid, rid, qty, uid)

    confirm_msg = (
        f"📦 *Solicitud de transferencia*\n\n"
        f"De: {rest_label(other_rest['name'])}\n"
        f"A: {rest_label(rname)}\n"
        f"Cantidad: *{qty}* almuerzos\n\n"
        f"ID de transferencia: `{transfer_id}`\n"
        f"El jefe de cocina de {rest_label(other_rest['name'])} debe confirmar el envío con:\n"
        f"`/confirmar_envio`"
    )

    # Notify originating restaurant
    for tid in config.all_ids_for_restaurant(other_rest["name"]) | config.ADMIN_IDS:
        try:
            await ctx.application.bot.send_message(
                chat_id=tid, text=confirm_msg, parse_mode="Markdown"
            )
        except Exception:
            pass

    # Notify requesting restaurant too
    await update.message.reply_text(
        f"✅ Solicitud enviada a {rest_label(other_rest['name'])}.\n"
        f"Esperando confirmación de envío.",
        parse_mode="Markdown"
    )


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_confirmar_envio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Confirma que los almuerzos ya fueron enviados por taxi."""
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    transfer = db.get_pending_transfer(rid)
    if not transfer:
        await update.message.reply_text(
            "❌ No hay transferencia pendiente para confirmar.\n"
            "Usa /transferir para solicitar una."
        )
        return

    if transfer["status"] != "requested":
        await update.message.reply_text(
            f"⚠️ Esta transferencia ya está en estado: *{transfer['status']}*",
            parse_mode="Markdown"
        )
        return

    db.update_transfer_status(transfer["id"], "sent")
    to_rest = db.get_restaurant_by_id(transfer["to_restaurant"])

    msg = (
        f"🚕 *Almuerzos en camino*\n\n"
        f"De: {rest_label(rname)}\n"
        f"A: {rest_label(to_rest['name'])}\n"
        f"Cantidad: *{transfer['quantity']}*\n\n"
        f"Cuando lleguen, confirma con `/confirmar_llegada`"
    )

    for tid in (config.all_ids_for_restaurant(rname) |
                config.all_ids_for_restaurant(to_rest["name"]) |
                config.ADMIN_IDS):
        try:
            await ctx.application.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
        except Exception:
            pass


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_confirmar_llegada(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Confirma que los almuerzos llegaron y suma al contador."""
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    transfer = db.get_pending_transfer(rid)
    if not transfer:
        await update.message.reply_text("❌ No hay transferencia activa.")
        return

    if transfer["status"] != "sent":
        await update.message.reply_text(
            f"⚠️ La transferencia está en estado: *{transfer['status']}*\n"
            f"Solo puedes confirmar llegada cuando está 'en camino'.",
            parse_mode="Markdown"
        )
        return

    qty = transfer["quantity"]
    to_rid = transfer["to_restaurant"]

    # Determine which restaurant is receiving
    if to_rid == rid:
        db.adjust_qty(rid, qty)
        db.update_transfer_status(transfer["id"], "received")
        new_qty = db.get_current_qty(rid)

        from_rest = db.get_restaurant_by_id(transfer["from_restaurant"])
        msg = (
            f"✅ *Transferencia recibida*\n\n"
            f"De: {rest_label(from_rest['name'])}\n"
            f"A: {rest_label(rname)}\n"
            f"Cantidad: *{qty}*\n"
            f"Nuevo total: *{new_qty}* almuerzos"
        )
        for tid in (config.all_ids_for_restaurant(rname) |
                    config.all_ids_for_restaurant(from_rest["name"]) |
                    config.ADMIN_IDS):
            try:
                await ctx.application.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
            except Exception:
                pass
    else:
        await update.message.reply_text(
            "❌ Solo el restaurante receptor puede confirmar la llegada."
        )
