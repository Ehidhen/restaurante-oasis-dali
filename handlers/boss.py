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
        shortages_today = db.get_all_shortages_today(rest["id"])
        pending_shortages = [s for s in shortages_today if s["status"] == "pending"]
        transfers = db.get_today_transfers(rest["id"])

        alm_qty, alm_tot = summary.get("almuerzo", (0, 0.0))
        total = summary.get("total", 0.0)

        estado = "❌ SIN ALMUERZOS" if qty == 0 else (f"⚠️ Pocas: {qty}" if qty <= config.ALERT_LOW_THRESHOLD else f"✅ {qty} disponibles")

        s = [
            f"{rest_label(rest['name'])}",
            f"Estado: {estado}",
        ]
        if menu:
            s.append(f"Menú: {menu['main_dish'] or '—'} | Bs {menu['price']:.2f}")
        s.append(f"Vendidos hoy: {alm_qty} almuerzos — Bs {total:.2f}")
        if pending_shortages:
            s.append(f"🛒 Faltantes hoy: {len(pending_shortages)} pendiente(s)")
        if transfers:
            s.append(f"↔️ Transferencias hoy: {len(transfers)}")

        sections.append("\n".join(s))

    oasis_sum = db.get_daily_summary(oasis["id"])
    dali_sum = db.get_daily_summary(dali["id"])
    grand = oasis_sum.get("total", 0.0) + dali_sum.get("total", 0.0)

    msg = (
        f"👁 *Vista general — Ambos restaurantes*\n"
        f"{'═' * 32}\n\n" +
        "\n\n".join(sections) +
        f"\n\n{'─' * 32}\n"
        f"💰 *Total combinado hoy: Bs {grand:.2f}*\n\n"
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
        "mesero": "Mesero/a 🍽",
    }

    commands_by_role = {
        "boss": (
            "📊 *Reportes*\n"
            "/overview — Vista completa de ambos restaurantes\n"
            "/resumen_hoy — Ventas del día\n"
            "/resumen_semana — Resumen semanal\n"
            "/comparar — Comparativa Oasis vs Dali\n"
            "/cuadre — Cuadre diario: comandas + ventas + pagos\n\n"
            "🍽 *Menú / Stock*\n"
            "/menu_hoy — Menú del día\n"
            "/quedan — Almuerzos disponibles\n"
            "/faltantes — Faltantes de hoy\n"
            "/mesas — Mesas activas de ambos restaurantes\n\n"
            "💳 *Pagos*\n"
            "/ver_pagos oasis — Comprobantes hoy Oasis\n"
            "/ver_pagos dali — Comprobantes hoy Dali\n"
            "/comprobantes_dia YYYY-MM-DD [oasis|dali]\n\n"
            "🌐 Panel web: " + config.WEB_URL
        ),
        "supervisor": (
            "📋 *Ver estado*\n"
            "/menu_hoy — Menú del día\n"
            "/quedan — Almuerzos disponibles\n"
            "/resumen_hoy — Ventas del día\n"
            "/faltantes — Faltantes pendientes hoy\n"
            "/ver_promos — Promos activas\n\n"
            "🪑 *Mesas*\n"
            "/mesas — Ver todas las mesas y estado de pedidos\n\n"
            "📋 *Comandas*\n"
            "/pedidos — Ver todos los pedidos del día\n"
            "/listo 5 — Marcar pedido #5 como listo\n\n"
            "🛒 *Inventario*\n"
            "/agregar_faltante Ítem | Cantidad\n"
            "/marcar_comprado Ítem\n"
            "/checklist — Checklist fin de turno\n\n"
            "↔️ *Transferencias*\n"
            "/transferir N — Solicitar N almuerzos del otro restaurante\n"
            "/confirmar_envio — Confirmar que salieron\n"
            "/confirmar_llegada — Confirmar que llegaron\n\n"
            "💳 *Caja*\n"
            "/ver_pagos — Comprobantes de hoy\n"
            "/cerrar_caja — Resumen del turno actual\n"
            "/cuadre — Cuadre: comandas + ventas + pagos QR\n"
            "/comprobantes_dia YYYY-MM-DD — Comprobantes de un día"
        ),
        "kitchen_chief": (
            "🍽 *Menú*\n"
            "/definir_menu Sopa | Plato | Refresco | Precio | Cantidad\n"
            "/agregar_extra Nombre | Precio\n"
            "/precio N — Cambiar precio del almuerzo\n\n"
            "🔢 *Stock*\n"
            "/quedan — Almuerzos disponibles ahora\n"
            "/ajustar N — Corregir contador\n"
            "/sin_almuerzos — Marcar agotado\n\n"
            "🪑 *Mesas*\n"
            "/mesas — Ver todas las mesas y estado de pedidos\n\n"
            "📋 *Comandas (pedidos de meseros)*\n"
            "/pedidos — Ver todos los pedidos del día\n"
            "/listo 5 — Marcar pedido #5 como listo (avisa al mesero)\n\n"
            "🛒 *Inventario (turno)*\n"
            "/faltantes — Ver faltantes de hoy\n"
            "/agregar_faltante Ítem | Cantidad\n"
            "/marcar_comprado Ítem\n"
            "/checklist — Planilla fin de turno\n"
            "/stock_ok — Confirmar stock completo\n\n"
            "↔️ *Transferencias*\n"
            "/transferir N — Solicitar almuerzos\n"
            "/confirmar_envio — Confirmar envío\n"
            "/confirmar_llegada — Confirmar llegada"
        ),
        "cashier": (
            "🍽 *Ventas*\n"
            "/menu_hoy — Ver menú del día\n"
            "/quedan — Almuerzos disponibles ahora\n"
            "/venta — Registrar 1 almuerzo\n"
            "/venta N — Registrar N almuerzos\n"
            "/resumen_hoy — Ventas del día\n\n"
            "💳 *Caja*\n"
            "/registrar_pago [monto] [desc] — Foto comprobante QR\n"
            "/ver_pagos — Comprobantes de hoy\n"
            "/cerrar_caja — Resumen turno actual\n"
            "/cerrar_caja manana — Ver turno mañana\n"
            "/cerrar_caja noche — Ver turno noche\n\n"
            "🧾 *Cuadre (sin papel)*\n"
            "/cuadre — Comandas + ventas + pagos en un vistazo\n"
            "/comprobantes_dia YYYY-MM-DD — Histórico de un día"
        ),
        "mesero": (
            "🏠 *Restaurante*\n"
            "/mi_restaurante — Ver dónde estás trabajando\n"
            "/mi_restaurante oasis — Cambiar a Oasis\n"
            "/mi_restaurante dali — Cambiar a Dali\n\n"
            "🪑 *Mesas*\n"
            "/mis_mesas 1 2 3 4 — Asignar mis mesas del turno\n"
            "/mis_mesas — Ver estado de mis mesas\n"
            "/mis_mesas limpiar — Liberar todas mis mesas\n"
            "/mesas — Ver todas las mesas del restaurante\n\n"
            "📋 *Comandas (pedidos)*\n"
            "/pedido Mesa 3 | 2 almuerzos + 1 extra — Registrar pedido\n"
            "/pedido 1 almuerzo                      ← sin mesa también\n"
            "/mis_pedidos — Ver tus pedidos agrupados por mesa\n"
            "/entregado 5 — Confirmar entrega del pedido #5\n\n"
            "💳 *Pagos QR*\n"
            "/registrar_pago [monto] [desc] — Registrar comprobante\n"
            "/comprobantes_dia YYYY-MM-DD — Tus comprobantes de ese día\n\n"
            "🍽 *Info*\n"
            "/menu_hoy — Ver menú del día\n"
            "/quedan — Almuerzos disponibles\n"
            "/ver_promos — Promos activas"
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
