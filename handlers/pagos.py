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
    """00:00–15:59 → mañana (almuerzo o pre-turno), 16:00–23:59 → noche."""
    hour = datetime.now().hour
    return SHIFT_MANANA if hour < 16 else SHIFT_NOCHE


def shift_label(shift: str) -> str:
    return "Turno Mañana (hasta 16:00)" if shift == SHIFT_MANANA else "Turno Noche (16:00–23:59)"


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

    rid    = ctx.user_data["restaurant_id"]
    rname  = ctx.user_data["restaurant_name"]

    if not rid:
        await update.message.reply_text(
            "👑 Especifica el restaurante:\n"
            "`/registrar_pago oasis 35 QR mesa 5`\n"
            "`/registrar_pago dali 40 efectivo`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    ctx.user_data["pago_amount"]      = amount
    ctx.user_data["pago_description"] = description

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
    role  = ctx.user_data["role"]
    today = db.today()

    # Boss without restaurant arg → show both
    if role == "boss" and not rid:
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            msgs.append(_format_pagos_hoy(rest["id"], name, today))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    await update.message.reply_text(_format_pagos_hoy(rid, rname, today), parse_mode="Markdown")


def _format_pagos_hoy(rid: int, rname: str, today: str) -> str:
    pagos = db.get_payments_by_date(rid, today)
    if not pagos:
        return f"{rest_label(rname)}\n📅 {today}\n❌ Sin comprobantes hoy."

    icons = {"verified": "✅", "wrong_account": "⚠️", "unreadable": "❓", "pending": "⏳"}
    lines = [f"{rest_label(rname)} — Comprobantes de hoy ({today})\n"]
    total = 0.0
    for p in pagos:
        t     = p["registered_at"][11:16] if p["registered_at"] else "—"
        icon  = icons.get(p["verification_status"], "⏳")
        turno = "☀️" if (p["shift"] or "") == "manana" else "🌙"
        total += p["amount"] or 0
        lines.append(f"{turno}{icon} #{p['id']} {t} — *Bs {p['amount']:.2f}* {p['cashier_name']}")

    lines.append(f"\n💰 Total: *Bs {total:.2f}*")
    return "\n".join(lines)


# ── Cerrar caja ───────────────────────────────────────────────────────────────

@require_role("cashier", "supervisor", "boss")
async def cmd_cerrar_caja(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /cerrar_caja             — Resumen del turno actual.
    /cerrar_caja manana      — Ver turno mañana.
    /cerrar_caja noche       — Ver turno noche.
    /cerrar_caja oasis       — Boss: ver turno actual de Oasis.
    /cerrar_caja dali noche  — Boss: ver turno noche de Dali.
    """
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    role  = ctx.user_data["role"]

    # Shift from argument or auto-detect
    arg = (ctx.args[0].lower().strip() if ctx.args else "").replace("ñ", "n")
    if arg in ("manana", "mañana"):
        shift = SHIFT_MANANA
    elif arg == "noche":
        shift = SHIFT_NOCHE
    else:
        shift = get_current_shift()

    # Boss without restaurant → show both restaurants
    if role == "boss" and not rid:
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            msgs.append(_build_cierre(rest["id"], name, shift))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    await update.message.reply_text(_build_cierre(rid, rname, shift), parse_mode="Markdown")


def _build_cierre(rid: int, rname: str, shift: str) -> str:
    pagos = db.get_payments_by_shift(rid, shift)

    verified   = [p for p in pagos if p["verification_status"] == "verified"]
    wrong      = [p for p in pagos if p["verification_status"] == "wrong_account"]
    unreadable = [p for p in pagos if p["verification_status"] == "unreadable"]
    pending    = [p for p in pagos if p["verification_status"] == "pending"]

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
        f"\n💰 *Total: Bs {total_all:.2f}*  ·  {len(pagos)} comprobante(s)\n",
    ]

    if wrong:
        lines.append("⚠️ *Comprobantes con cuenta incorrecta:*")
        for p in wrong:
            t = (p["registered_at"] or "")[11:16]
            lines.append(f"  #{p['id']} {t} Bs {p['amount']:.2f} — {p['cashier_name']}")
            if p["extracted_account"]:
                lines.append(f"  Cuenta detectada: `{p['extracted_account']}`")
        lines.append("")

    if unreadable:
        lines.append("❓ *Comprobantes ilegibles (revisar manualmente):*")
        for p in unreadable:
            t = (p["registered_at"] or "")[11:16]
            lines.append(f"  #{p['id']} {t} Bs {p['amount']:.2f} — {p['cashier_name']}")
        lines.append("")

    if can_close:
        lines.append("✅ *Todo en orden — caja puede cerrarse.*")
    else:
        lines.append("🚫 *Caja NO puede cerrarse aún.*")
        lines.append("Resuelve los ⚠️ o ❓ primero.")

    return "\n".join(lines)


# ── Cuadre del día ───────────────────────────────────────────────────────────

@require_role("cashier", "supervisor", "boss")
async def cmd_cuadre(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /cuadre — Vista completa para el cuadre de caja:
    Comandas de meseros + Ventas registradas + Pagos QR = cierre del día sin papel.
    """
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    role  = ctx.user_data["role"]

    if role == "boss" and not rid:
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            msgs.append(_build_cuadre(rest["id"], name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    await update.message.reply_text(_build_cuadre(rid, rname), parse_mode="Markdown")


def _build_cuadre(rid: int, rname: str) -> str:
    today = db.today()

    # ── 1. Comandas de meseros ────────────────────────────────────────────────
    orders   = db.get_orders_today(rid)
    servidos = [o for o in orders if o["status"] == "served"]
    listos   = [o for o in orders if o["status"] == "ready"]
    cocina   = [o for o in orders if o["status"] == "pending"]

    # Contar almuerzos de las comandas servidas (extraer números del campo items)
    import re as _re
    alm_en_comandas = 0
    for o in servidos:
        nums = _re.findall(r"(\d+)\s*almuerzo", o["items"], flags=_re.IGNORECASE)
        alm_en_comandas += sum(int(n) for n in nums) if nums else 1

    # ── 2. Ventas registradas por caja ────────────────────────────────────────
    summary  = db.get_daily_summary(rid)
    alm_qty, alm_tot = summary.get("almuerzo", (0, 0.0))
    ext_qty, ext_tot = summary.get("extra",    (0, 0.0))
    ref_qty, ref_tot = summary.get("refresco", (0, 0.0))
    total_ventas     = summary.get("total", 0.0)

    # ── 3. Pagos QR recibidos ─────────────────────────────────────────────────
    pagos          = db.get_payments_by_date(rid, today)
    total_pagos    = sum(p["amount"] or 0 for p in pagos)
    pagos_ok       = [p for p in pagos if p["verification_status"] == "verified"]
    pagos_wrong    = [p for p in pagos if p["verification_status"] == "wrong_account"]
    pagos_pend     = [p for p in pagos if p["verification_status"] in ("pending", "unreadable")]
    total_ok       = sum(p["amount"] or 0 for p in pagos_ok)

    # ── Diferencia ────────────────────────────────────────────────────────────
    diferencia = total_ventas - total_pagos  # positivo = posible efectivo

    lines = [
        f"🧾 *Cuadre del día — {rest_label(rname)}*",
        f"📅 {today}\n",

        f"📋 *Comandas (meseros):*",
        f"  ✅ Servidas hoy: *{len(servidos)}*",
    ]
    if alm_en_comandas:
        lines.append(f"  🍽 Almuerzos en comandas: *{alm_en_comandas}*")
    if listos:
        lines.append(f"  🔔 Listas sin recoger: {len(listos)}")
    if cocina:
        lines.append(f"  ⏳ En cocina aún: {len(cocina)}")
    lines.append(f"  📊 Total comandas hoy: {len(orders)}\n")

    lines += [
        f"💵 *Ventas registradas (caja):*",
        f"  🍽 {alm_qty} almuerzos — Bs {alm_tot:.2f}",
    ]
    if ext_qty:
        lines.append(f"  🍴 {ext_qty} extras — Bs {ext_tot:.2f}")
    if ref_qty:
        lines.append(f"  🥤 {ref_qty} refrescos — Bs {ref_tot:.2f}")
    lines.append(f"  💰 Total ventas: *Bs {total_ventas:.2f}*\n")

    lines += [
        f"💳 *Pagos QR recibidos ({len(pagos)}):*",
        f"  ✅ Verificados: {len(pagos_ok)} — Bs {total_ok:.2f}",
    ]
    if pagos_wrong:
        lines.append(f"  ⚠️ Cuenta incorrecta: {len(pagos_wrong)} — Bs {sum(p['amount'] or 0 for p in pagos_wrong):.2f}")
    if pagos_pend:
        lines.append(f"  ❓ Por verificar: {len(pagos_pend)}")
    lines.append(f"  💳 Total pagos: *Bs {total_pagos:.2f}*\n")

    # ── Línea de cuadre ───────────────────────────────────────────────────────
    lines.append(f"{'─' * 30}")
    lines.append(f"💰 Ventas:   *Bs {total_ventas:.2f}*")
    lines.append(f"💳 QR cob.:  *Bs {total_pagos:.2f}*")

    if abs(diferencia) < 0.01:
        lines.append(f"✅ *Cuadre perfecto — todo encuadra*")
    elif diferencia > 0:
        lines.append(f"💵 *Bs {diferencia:.2f} en efectivo (probable)*")
    else:
        lines.append(f"🚨 *Diferencia Bs {abs(diferencia):.2f} — revisar pagos*")

    if pagos_wrong:
        lines.append(f"\n⚠️ _Hay comprobantes con cuenta incorrecta — revisar antes de cerrar._")

    return "\n".join(lines)


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
