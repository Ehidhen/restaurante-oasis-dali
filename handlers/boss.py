from telegram import Update
from telegram.ext import ContextTypes
import database as db
import config
from handlers.roles import require_role, rest_label


@require_role("boss")
async def cmd_overview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Vista completa del dueño: estado en tiempo real de los dos restaurantes."""
    oasis = db.get_restaurant("oasis")
    dali = db.get_restaurant("dali")

    sections = []
    for rest in [oasis, dali]:
        menu = db.get_menu(rest["id"])
        qty = db.get_current_qty(rest["id"])
        summary = db.get_daily_summary(rest["id"])
        shortages = db.get_shortages(rest["id"])
        transfers = db.get_today_transfers(rest["id"])

        alm_qty, alm_tot = summary.get("almuerzo", (0, 0.0))
        total = summary.get("total", 0.0)

        estado = "❌ SIN ALMUERZOS" if qty == 0 else (f"⚠️ Pocas: {qty}" if qty <= config.ALERT_LOW_THRESHOLD else f"✅ {qty} disponibles")

        s = [
            f"{rest_label(rest['name'])}",
            f"Estado: {estado}",
        ]
        if menu:
            s.append(f"Menú: {menu['main_dish'] or '—'} | ${menu['price']:.2f}")
        s.append(f"Vendidos hoy: {alm_qty} almuerzos — ${total:.2f}")
        if shortages:
            s.append(f"Faltantes: {len(shortages)} ítems pendientes")
        if transfers:
            s.append(f"Transferencias hoy: {len(transfers)}")

        sections.append("\n".join(s))

    oasis_sum = db.get_daily_summary(oasis["id"])
    dali_sum = db.get_daily_summary(dali["id"])
    grand = oasis_sum.get("total", 0.0) + dali_sum.get("total", 0.0)

    msg = (
        f"👁 *Vista general — Ambos restaurantes*\n"
        f"{'═' * 32}\n\n" +
        "\n\n".join(sections) +
        f"\n\n{'─' * 32}\n"
        f"💰 *Total combinado hoy: ${grand:.2f}*\n\n"
        f"🌐 Panel web: {config.WEB_URL}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Auto-register user on first contact and show available commands."""
    uid = str(update.effective_user.id)
    full_name = update.effective_user.full_name

    role, rest_name = config.get_role_and_restaurant(uid)

    if role is None:
        await update.message.reply_text(
            "👋 Hola, bienvenido.\n\n"
            "No tienes un rol asignado aún. Contacta al administrador."
        )
        return

    rest = db.get_restaurant(rest_name) if rest_name else None
    rid = rest["id"] if rest else None
    db.upsert_user(uid, full_name, role, rid)

    role_labels = {
        "boss": "Dueño 👑",
        "supervisor": "Supervisora 👩‍💼",
        "kitchen_chief": "Jefe de Cocina 👨‍🍳",
        "cashier": "Cajero/a 💵",
    }

    commands_by_role = {
        "boss": (
            "/overview — Vista completa de ambos restaurantes\n"
            "/menu_hoy — Menú del día\n"
            "/quedan — Almuerzos disponibles\n"
            "/resumen_hoy — Ventas del día\n"
            "/resumen_semana — Resumen semanal\n"
            "/comparar — Comparativa Oasis vs Dali\n"
            "/faltantes — Lista de faltantes"
        ),
        "supervisor": (
            "/menu_hoy — Menú del día\n"
            "/quedan — Almuerzos disponibles\n"
            "/resumen_hoy — Ventas del día\n"
            "/faltantes — Faltantes pendientes\n"
            "/agregar_faltante Ítem | Cantidad\n"
            "/transferir N — Solicitar almuerzos\n"
            "/confirmar_envio — Confirmar envío\n"
            "/confirmar_llegada — Confirmar llegada"
        ),
        "kitchen_chief": (
            "/definir_menu Sopa | Plato | Refresco | Precio | Cantidad\n"
            "/agregar_extra Nombre | Precio\n"
            "/precio N — Cambiar precio del almuerzo\n"
            "/quedan — Almuerzos disponibles\n"
            "/ajustar N — Corregir contador\n"
            "/sin_almuerzos — Marcar agotado\n"
            "/faltantes — Ver faltantes\n"
            "/agregar_faltante Ítem | Cantidad\n"
            "/marcar_comprado Ítem\n"
            "/checklist — Checklist fin de turno\n"
            "/stock_ok — Confirmar stock completo\n"
            "/transferir N — Solicitar/enviar almuerzos\n"
            "/confirmar_envio — Confirmar envío\n"
            "/confirmar_llegada — Confirmar llegada"
        ),
        "cashier": (
            "/menu_hoy — Ver menú del día\n"
            "/quedan — Almuerzos disponibles\n"
            "/venta — Registrar 1 almuerzo\n"
            "/venta N — Registrar N almuerzos\n"
            "/resumen_hoy — Ventas del día"
        ),
    }

    rest_info = f" — {rest_label(rest_name)}" if rest_name else ""
    await update.message.reply_text(
        f"✅ ¡Hola, {full_name}!\n"
        f"Rol: *{role_labels.get(role, role)}{rest_info}*\n\n"
        f"*Comandos disponibles:*\n{commands_by_role.get(role, '')}",
        parse_mode="Markdown"
    )


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)
