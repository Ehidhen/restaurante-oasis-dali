"""Registro de comprobantes de pago y cierre de caja por turno."""
import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, MessageHandler, filters
)

import config
import database as db
from handlers.roles import require_role, rest_label
from handlers.vision import analyze_comprobante

logger = logging.getLogger(__name__)

WAITING_COMPROBANTE = 0
COMPROBANTES_DIR = os.getenv("COMPROBANTES_DIR", "comprobantes")

SHIFT_MANANA = "manana"
SHIFT_NOCHE  = "noche"


def _ensure_dir():
    os.makedirs(COMPROBANTES_DIR, exist_ok=True)


def get_current_shift() -> str:
    hour = datetime.now().hour
    return SHIFT_MANANA if 11 <= hour < 16 else SHIFT_NOCHE


def shift_label(shift: str) -> str:
    return "Turno Mañana (11:00–16:00)" if shift == SHIFT_MANANA else "Turno Noche (16:00–23:00)"


# ── Registro de comprobante ──────────────────────────────────────────────────

@require_role("cashier", "supervisor", "boss", "mesero")
async def cmd_registrar_pago(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /registrar_pago [monto] [descripcion]
    Ejemplo: /registrar_pago 35 QR mesa 5
    """
    args = " ".join(ctx.args) if ctx.args else ""
    parts = args.strip().split(None, 1)

    amount, description = 0.0, ""
    if parts:
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            description = args
    if len(parts) > 1:
        description = parts[1]

    ctx.user_data["pago_amount"]      = amount
    ctx.user_data["pago_description"] = description

    rname  = ctx.user_data["restaurant_name"]
    shift  = get_current_shift()
    amt_s  = f"Bs {amount:.2f}" if amount else "(sin monto)"

    await update.message.reply_text(
        f"💳 *Registrar comprobante — {rest_label(rname)}*\n"
        f"📋 {shift_label(shift)}\n\n"
        f"💰 Monto: *{amt_s}*\n"
        f"{f'📝 {description}' if description else ''}\n\n"
        f"📸 Envía la *foto del comprobante* de pago.\n"
        f"_(o /cancelar para abortar)_",
        parse_mode="Markdown"
    )
    return WAITING_COMPROBANTE


async def handle_comprobante_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid    = ctx.user_data["restaurant_id"]
    rname  = ctx.user_data["restaurant_name"]
    cashier = (ctx.user_data.get("username")
               or update.effective_user.full_name
               or update.effective_user.first_name
               or "Caja")
    amount  = ctx.user_data.get("pago_amount", 0.0)
    desc    = ctx.user_data.get("pago_description", "")
    shift   = get_current_shift()

    photo   = update.message.photo[-1]
    file_id = photo.file_id
    file_path = ""

    _ensure_dir()
    local_path = ""
    try:
        tg_file = await ctx.bot.get_file(file_id)
        filename = f"{rid}_{update.effective_user.id}_{photo.file_unique_id}.jpg"
        local_path = os.path.join(COMPROBANTES_DIR, filename)
        await tg_file.download_to_drive(local_path)
        file_path = filename
    except Exception as e:
        logger.warning(f"No se pudo descargar comprobante: {e}")

    # ── Análisis con IA ──────────────────────────────────────────────────────
    vision_result = {"cuenta_destino": None, "monto": None, "error": None}
    if local_path and os.path.exists(local_path):
        await update.message.reply_text("🔍 Analizando comprobante con IA…")
        vision_result = analyze_comprobante(local_path)

    extracted_account = vision_result.get("cuenta_destino") or ""
    extracted_amount  = vision_result.get("monto") or 0.0

    # Verificación automática de cuenta
    v_status = config.verify_account(extracted_account, rname)

    pid = db.add_payment(
        restaurant_id=rid,
        cashier_name=cashier,
        amount=amount,
        description=desc,
        file_id=file_id,
        file_path=file_path,
        shift=shift,
        verification_status=v_status,
        extracted_account=extracted_account,
        extracted_amount=extracted_amount,
    )

    # Respuesta según resultado de verificación
    status_icons = {
        "verified":      "✅ *Cuenta verificada*",
        "wrong_account": "⚠️ *CUENTA INCORRECTA* — revisar",
        "unreadable":    "❓ *No se pudo leer la cuenta* — revisar manualmente",
        "pending":       "⏳ *Cuenta no configurada* — registrar en sistema",
    }
    status_line = status_icons.get(v_status, "❓")

    account_line = ""
    if extracted_account:
        account_line = f"🏦 Cuenta detectada: `{extracted_account}`\n"
    amount_ai = f"💰 Monto leído por IA: Bs {extracted_amount:.2f}\n" if extracted_amount else ""

    await update.message.reply_text(
        f"{status_line}\n\n"
        f"💳 *Comprobante #{pid} — {rest_label(rname)}*\n"
        f"📋 {shift_label(shift)}\n"
        f"💰 Monto registrado: Bs {amount:.2f}\n"
        f"{amount_ai}"
        f"{account_line}"
        f"👤 Caja: {cashier}\n"
        f"{f'📝 {desc}' if desc else ''}\n\n"
        f"Ver todos: panel web → 💳 Caja",
        parse_mode="Markdown"
    )

    # Alerta si cuenta incorrecta
    if v_status == "wrong_account":
        expected = config.get_restaurant_account(rname)
        alert_msg = (
            f"🚨 *ALERTA — Comprobante con cuenta incorrecta*\n\n"
            f"Restaurante: {rest_label(rname)}\n"
            f"Cajera: {cashier}\n"
            f"Monto: Bs {amount:.2f}\n"
            f"Cuenta detectada: `{extracted_account}`\n"
            f"Cuenta esperada: `{config.OASIS_ACCOUNT_RAW if rname == 'oasis' else config.DALI_ACCOUNT_RAW}`\n\n"
            f"Verificar el comprobante #{pid} inmediatamente."
        )
        supervisors = (
            config.OASIS_SUPERVISOR_IDS if rname == "oasis" else config.DALI_SUPERVISOR_IDS
        ) | config.ADMIN_IDS
        for tid in supervisors:
            try:
                await ctx.bot.send_message(chat_id=tid, text=alert_msg, parse_mode="Markdown")
            except Exception:
                pass

    return ConversationHandler.END


# ── Ver pagos ────────────────────────────────────────────────────────────────

@require_role("cashier", "supervisor", "boss")
async def cmd_ver_pagos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    pagos = db.get_payments(rid, limit=15)
    if not pagos:
        await update.message.reply_text(f"{rest_label(rname)}\n❌ Sin comprobantes hoy.")
        return

    icons = {"verified": "✅", "wrong_account": "⚠️", "unreadable": "❓", "pending": "⏳"}
    lines = [f"{rest_label(rname)} — Últimos comprobantes\n"]
    total = 0.0
    for p in pagos:
        t = p["registered_at"][11:16] if p["registered_at"] else "—"
        icon = icons.get(p["verification_status"], "⏳")
        amt = f"Bs {p['amount']:.2f}"
        total += p["amount"] or 0
        lines.append(f"{icon} #{p['id']} {t} — *{amt}* {p['cashier_name']}")

    lines.append(f"\n💰 Total: *Bs {total:.2f}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Cerrar caja ───────────────────────────────────────────────────────────────

@require_role("cashier", "supervisor", "boss")
async def cmd_cerrar_caja(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /cerrar_caja — Resumen del turno actual con estado de cada comprobante.
    """
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    shift = get_current_shift()

    pagos = db.get_payments_by_shift(rid, shift)

    verified      = [p for p in pagos if p["verification_status"] == "verified"]
    wrong         = [p for p in pagos if p["verification_status"] == "wrong_account"]
    unreadable    = [p for p in pagos if p["verification_status"] == "unreadable"]
    pending       = [p for p in pagos if p["verification_status"] == "pending"]

    total_all      = sum(p["amount"] or 0 for p in pagos)
    total_verified = sum(p["amount"] or 0 for p in verified)

    can_close = len(wrong) == 0 and len(unreadable) == 0 and len(pending) == 0

    lines = [
        f"🗂 *Cierre de caja — {rest_label(rname)}*",
        f"📋 {shift_label(shift)}\n",
        f"📊 *Resumen:*",
        f"  ✅ Verificados: {len(verified)} — Bs {total_verified:.2f}",
        f"  ⚠️ Cuenta incorrecta: {len(wrong)}",
        f"  ❓ Ilegibles: {len(unreadable)}",
        f"  ⏳ Pendientes: {len(pending)}",
        f"\n💰 *Total comprobantes: Bs {total_all:.2f}*",
        f"📝 *Total comprobantes: {len(pagos)}*\n",
    ]

    if wrong:
        lines.append("⚠️ *Comprobantes con cuenta incorrecta:*")
        for p in wrong:
            t = p["registered_at"][11:16]
            lines.append(f"  #{p['id']} {t} Bs {p['amount']:.2f} — {p['cashier_name']}")
            if p["extracted_account"]:
                lines.append(f"  Cuenta detectada: `{p['extracted_account']}`")
        lines.append("")

    if unreadable:
        lines.append("❓ *Comprobantes ilegibles (verificar manualmente):*")
        for p in unreadable:
            t = p["registered_at"][11:16]
            lines.append(f"  #{p['id']} {t} Bs {p['amount']:.2f} — {p['cashier_name']}")
        lines.append("")

    if can_close:
        lines.append("✅ *Todo en orden — caja puede cerrarse.*")
    else:
        lines.append("🚫 *Caja NO puede cerrarse aún.*")
        lines.append("Resuelve los comprobantes marcados con ⚠️ o ❓ primero.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Cancelar ─────────────────────────────────────────────────────────────────

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
