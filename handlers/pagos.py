"""Registro de comprobantes de pago para caja."""
import logging
import os

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, MessageHandler, filters
)

import database as db
from handlers.roles import require_role, rest_label

logger = logging.getLogger(__name__)

WAITING_COMPROBANTE = 0

COMPROBANTES_DIR = os.getenv("COMPROBANTES_DIR", "comprobantes")


def _ensure_dir():
    os.makedirs(COMPROBANTES_DIR, exist_ok=True)


@require_role("cashier", "supervisor", "boss")
async def cmd_registrar_pago(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /registrar_pago [monto] [descripcion]
    Ejemplo: /registrar_pago 35 QR mesa 5
    """
    args = " ".join(ctx.args) if ctx.args else ""
    parts = args.strip().split(None, 1)

    amount = 0.0
    description = ""
    if parts:
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            description = args
    if len(parts) > 1:
        description = parts[1]

    ctx.user_data["pago_amount"] = amount
    ctx.user_data["pago_description"] = description

    rname = ctx.user_data["restaurant_name"]
    amount_str = f"Bs {amount:.2f}" if amount else "(sin monto)"

    await update.message.reply_text(
        f"💳 *Registrar comprobante — {rest_label(rname)}*\n\n"
        f"💰 Monto: *{amount_str}*\n"
        f"{f'📝 Nota: {description}' if description else ''}\n\n"
        f"📸 Envía ahora la *foto del comprobante* de pago.\n"
        f"_(o /cancelar para abortar)_",
        parse_mode="Markdown"
    )
    return WAITING_COMPROBANTE


async def handle_comprobante_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    cashier = ctx.user_data.get("username") or update.effective_user.first_name or "Caja"
    amount = ctx.user_data.get("pago_amount", 0.0)
    description = ctx.user_data.get("pago_description", "")

    photo = update.message.photo[-1]
    file_id = photo.file_id
    file_path = ""

    _ensure_dir()
    try:
        tg_file = await ctx.bot.get_file(file_id)
        filename = f"{rid}_{update.effective_user.id}_{photo.file_unique_id}.jpg"
        local_path = os.path.join(COMPROBANTES_DIR, filename)
        await tg_file.download_to_drive(local_path)
        file_path = filename
    except Exception as e:
        logger.warning(f"No se pudo descargar comprobante: {e}")

    pid = db.add_payment(rid, cashier, amount, description, file_id, file_path)

    amount_str = f"Bs {amount:.2f}" if amount else "—"
    await update.message.reply_text(
        f"✅ *Comprobante registrado — {rest_label(rname)}*\n\n"
        f"💰 Monto: {amount_str}\n"
        f"👤 Caja: {cashier}\n"
        f"{f'📝 {description}' if description else ''}\n"
        f"🔑 ID: `#{pid}`\n\n"
        f"Visible en el panel web → sección CAJA.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cmd_ver_pagos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lista los últimos 10 comprobantes del restaurante."""
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    pagos = db.get_payments(rid, limit=10)
    if not pagos:
        await update.message.reply_text(f"{rest_label(rname)}\n❌ Sin comprobantes registrados hoy.")
        return

    lines = [f"{rest_label(rname)} — Últimos comprobantes\n"]
    total = 0.0
    for p in pagos:
        dt = p["registered_at"][11:16] if p["registered_at"] else "—"
        amount_str = f"Bs {p['amount']:.2f}" if p["amount"] else "—"
        total += p["amount"] or 0
        desc = f" · {p['description']}" if p["description"] else ""
        lines.append(f"#{p['id']} {dt} — *{amount_str}* {p['cashier_name']}{desc}")

    lines.append(f"\n💰 Total: *Bs {total:.2f}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel_pago(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registro de comprobante cancelado.")
    return ConversationHandler.END


def build_pagos_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("registrar_pago", cmd_registrar_pago)],
        states={
            WAITING_COMPROBANTE: [
                MessageHandler(filters.PHOTO, handle_comprobante_photo),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancel_pago)],
        conversation_timeout=180,
    )
