import logging
import os
from datetime import time, timezone, timedelta

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

import database as db
import config

from handlers.boss import cmd_start, cmd_ayuda, cmd_overview
from handlers.menu import cmd_menu_hoy, cmd_definir_menu, cmd_agregar_extra, cmd_precio
from handlers.ventas import cmd_quedan, cmd_venta, cmd_ajustar, cmd_sin_almuerzos
from handlers.inventario import (
    cmd_faltantes, cmd_agregar_faltante, cmd_marcar_comprado,
    cmd_checklist, cmd_stock_ok
)
from handlers.transferencias import cmd_transferir, cmd_confirmar_envio, cmd_confirmar_llegada
from handlers.reportes import cmd_resumen_hoy, cmd_resumen_semana, cmd_comparar

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# UTC-5 (Ecuador / Colombia / Peru)
LOCAL_TZ = timezone(timedelta(hours=-5))


# ── Jobs automáticos ────────────────────────────────────────────────────────

async def job_reporte_matutino(ctx: ContextTypes.DEFAULT_TYPE):
    """8:00 AM — Enviar lista de faltantes a supervisora y jefe de cocina."""
    for rest_name in ["oasis", "dali"]:
        rest = db.get_restaurant(rest_name)
        items = db.get_shortages(rest["id"], "pending")
        if not items:
            msg = (
                f"☀️ *Buenos días — {_rest_label(rest_name)}*\n\n"
                f"✅ No hay faltantes pendientes para hoy. ¡Todo listo!"
            )
        else:
            lines = [f"☀️ *Reporte matutino — {_rest_label(rest_name)}*\n",
                     f"📋 Faltantes pendientes de comprar:\n"]
            for i, item in enumerate(items, 1):
                lines.append(f"{i}. 🛒 {item['item_name']} — {item['quantity_needed']}")
            msg = "\n".join(lines)

        recipients = (
            (config.OASIS_SUPERVISOR_IDS | config.OASIS_CHIEF_IDS)
            if rest_name == "oasis"
            else (config.DALI_SUPERVISOR_IDS | config.DALI_CHIEF_IDS)
        )
        for tid in recipients:
            try:
                await ctx.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Reporte matutino no entregado a {tid}: {e}")


async def job_cierre_turno(ctx: ContextTypes.DEFAULT_TYPE):
    """10:00 PM — Recordar al jefe de cocina el checklist de faltantes."""
    for rest_name in ["oasis", "dali"]:
        msg = (
            f"🌙 *Cierre de turno — {_rest_label(rest_name)}*\n\n"
            f"Es hora de completar el checklist de faltantes.\n"
            f"Usa /checklist para ver el estado actual.\n"
            f"Usa /agregar_faltante para registrar lo que falta.\n"
            f"Confirma con /stock_ok cuando esté todo listo."
        )
        chiefs = config.OASIS_CHIEF_IDS if rest_name == "oasis" else config.DALI_CHIEF_IDS
        for tid in chiefs:
            try:
                await ctx.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Recordatorio cierre no entregado a {tid}: {e}")


async def job_check_cross_transfer(ctx: ContextTypes.DEFAULT_TYPE):
    """Cada 15 minutos — Si un restaurante tiene 0 y el otro >10, sugiere transferencia."""
    oasis = db.get_restaurant("oasis")
    dali  = db.get_restaurant("dali")
    o_qty = db.get_current_qty(oasis["id"])
    d_qty = db.get_current_qty(dali["id"])

    suggestions = []
    if o_qty == 0 and d_qty > 10:
        suggestions.append(("oasis", "dali", d_qty))
    if d_qty == 0 and o_qty > 10:
        suggestions.append(("dali", "oasis", o_qty))

    for needs, has, qty in suggestions:
        msg = (
            f"💡 *Sugerencia automática de transferencia*\n\n"
            f"{_rest_label(needs)} tiene 0 almuerzos.\n"
            f"{_rest_label(has)} tiene *{qty}* disponibles.\n\n"
            f"¿Solicitar transferencia?\nUsa: `/transferir <cantidad>`"
        )
        all_ids = (
            config.OASIS_SUPERVISOR_IDS | config.OASIS_CHIEF_IDS |
            config.DALI_SUPERVISOR_IDS  | config.DALI_CHIEF_IDS  |
            config.ADMIN_IDS
        )
        for tid in all_ids:
            try:
                await ctx.bot.send_message(chat_id=tid, text=msg, parse_mode="Markdown")
            except Exception:
                pass


def _rest_label(name: str) -> str:
    return "🌴 Oasis" if name == "oasis" else "🎨 Dali"


# ── Arranque ────────────────────────────────────────────────────────────────

def main():
    db.init_db()

    token = config.BOT_TOKEN
    if not token:
        raise ValueError("BOT_TOKEN no está configurado en .env")

    app = Application.builder().token(token).build()

    # ── Comandos generales ──
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("ayuda",   cmd_ayuda))
    app.add_handler(CommandHandler("help",    cmd_ayuda))

    # ── Vista del dueño ──
    app.add_handler(CommandHandler("overview",      cmd_overview))

    # ── Menú ──
    app.add_handler(CommandHandler("menu_hoy",      cmd_menu_hoy))
    app.add_handler(CommandHandler("definir_menu",  cmd_definir_menu))
    app.add_handler(CommandHandler("agregar_extra", cmd_agregar_extra))
    app.add_handler(CommandHandler("precio",        cmd_precio))

    # ── Ventas y almuerzos ──
    app.add_handler(CommandHandler("quedan",        cmd_quedan))
    app.add_handler(CommandHandler("venta",         cmd_venta))
    app.add_handler(CommandHandler("ajustar",       cmd_ajustar))
    app.add_handler(CommandHandler("sin_almuerzos", cmd_sin_almuerzos))

    # ── Inventario ──
    app.add_handler(CommandHandler("faltantes",        cmd_faltantes))
    app.add_handler(CommandHandler("agregar_faltante", cmd_agregar_faltante))
    app.add_handler(CommandHandler("marcar_comprado",  cmd_marcar_comprado))
    app.add_handler(CommandHandler("checklist",        cmd_checklist))
    app.add_handler(CommandHandler("stock_ok",         cmd_stock_ok))

    # ── Transferencias ──
    app.add_handler(CommandHandler("transferir",         cmd_transferir))
    app.add_handler(CommandHandler("confirmar_envio",    cmd_confirmar_envio))
    app.add_handler(CommandHandler("confirmar_llegada",  cmd_confirmar_llegada))

    # ── Reportes ──
    app.add_handler(CommandHandler("resumen_hoy",    cmd_resumen_hoy))
    app.add_handler(CommandHandler("resumen_semana", cmd_resumen_semana))
    app.add_handler(CommandHandler("comparar",       cmd_comparar))

    # ── Jobs programados ──
    job_queue = app.job_queue

    # 8:00 AM local
    job_queue.run_daily(
        job_reporte_matutino,
        time=time(hour=8, minute=0, tzinfo=LOCAL_TZ),
        name="reporte_matutino"
    )

    # 10:00 PM local
    job_queue.run_daily(
        job_cierre_turno,
        time=time(hour=22, minute=0, tzinfo=LOCAL_TZ),
        name="cierre_turno"
    )

    # Check cada 15 min para sugerir transferencias cruzadas
    job_queue.run_repeating(
        job_check_cross_transfer,
        interval=900,
        first=60,
        name="cross_transfer_check"
    )

    logger.info("Bot iniciado. Escuchando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
