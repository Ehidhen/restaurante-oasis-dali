"""
Comandos para meseros:
  /mi_restaurante [oasis|dali]  — Ver o cambiar el restaurante activo.
  /comprobantes_dia YYYY-MM-DD  — Ver/enviar comprobantes de un día específico.
"""
import logging
import os
import re
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
from handlers.roles import any_role, require_role, rest_label

logger = logging.getLogger(__name__)

COMPROBANTES_DIR = os.getenv("COMPROBANTES_DIR", "comprobantes")


# ── /mi_restaurante ──────────────────────────────────────────────────────────

@any_role
async def cmd_mi_restaurante(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /mi_restaurante           → muestra el restaurante actual
    /mi_restaurante oasis     → cambia a Oasis
    /mi_restaurante dali      → cambia a Dali
    Útil para meseros que trabajan en ambos restaurantes según el día.
    """
    uid      = str(update.effective_user.id)
    role     = ctx.user_data["role"]
    cur_name = ctx.user_data["restaurant_name"]

    # Solo mostrar, sin argumento
    if not ctx.args:
        nota = ""
        if role == "mesero":
            nota = "\n\nPara cambiar: `/mi_restaurante oasis` o `/mi_restaurante dali`"
        await update.message.reply_text(
            f"🏠 *Restaurante actual:* {rest_label(cur_name) if cur_name else 'No asignado'}"
            f"{nota}",
            parse_mode="Markdown"
        )
        return

    target = ctx.args[0].lower().strip()
    if target not in ("oasis", "dali"):
        await update.message.reply_text(
            "❌ Restaurante no válido.\n"
            "Usa: `/mi_restaurante oasis` o `/mi_restaurante dali`",
            parse_mode="Markdown"
        )
        return

    rest = db.get_restaurant(target)
    if not rest:
        await update.message.reply_text("❌ Error interno: restaurante no encontrado.")
        return

    # Asegurarse de que el usuario está en la BD
    user = db.get_user(uid)
    if not user:
        # Auto-registro con el restaurante base del config
        base_role, base_rest_name = config.get_role_and_restaurant(uid)
        if base_role is None:
            await update.message.reply_text("⛔ No tienes acceso registrado.")
            return
        base_rest = db.get_restaurant(base_rest_name) if base_rest_name else None
        base_rid  = base_rest["id"] if base_rest else None
        full_name = update.effective_user.full_name or "Mesero"
        db.upsert_user(uid, full_name, base_role, base_rid, current_restaurant_id=rest["id"])
    else:
        db.set_user_restaurant(uid, rest["id"])

    emoji = "🌴" if target == "oasis" else "🎨"
    await update.message.reply_text(
        f"✅ *Restaurante actualizado*\n\n"
        f"Ahora estás trabajando en: {emoji} *{target.capitalize()}*\n"
        f"Tus comprobantes se guardarán en este restaurante.",
        parse_mode="Markdown"
    )


# ── /comprobantes_dia ────────────────────────────────────────────────────────

@require_role("cashier", "supervisor", "boss", "mesero")
async def cmd_comprobantes_dia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /comprobantes_dia YYYY-MM-DD [oasis|dali]

    Muestra el resumen de comprobantes de un día específico y envía las fotos.
    El dueño puede especificar el restaurante. Los demás ven el suyo.
    """
    role  = ctx.user_data["role"]
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    args = ctx.args or []
    date_str   = None
    target_rest = None

    for arg in args:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", arg):
            date_str = arg
        elif arg.lower() in ("oasis", "dali"):
            target_rest = arg.lower()

    if not date_str:
        today = db.today()
        await update.message.reply_text(
            "📅 *Uso:* `/comprobantes_dia YYYY-MM-DD`\n"
            f"Ejemplo: `/comprobantes_dia {today}`\n\n"
            "_(El dueño puede añadir el restaurante: `... oasis` o `... dali`)_",
            parse_mode="Markdown"
        )
        return

    # El dueño puede pedir cualquier restaurante
    if role == "boss":
        if target_rest:
            rest = db.get_restaurant(target_rest)
            if not rest:
                await update.message.reply_text("❌ Restaurante no encontrado.")
                return
            rid   = rest["id"]
            rname = target_rest
        elif not rid:
            # Boss sin restaurante y sin arg → mostrar ambos
            msgs = []
            for name in ["oasis", "dali"]:
                rest = db.get_restaurant(name)
                p = db.get_payments_by_date(rest["id"], date_str)
                if p:
                    total = sum(x["amount"] or 0 for x in p)
                    msgs.append(
                        f"{rest_label(name)} — {date_str}: "
                        f"{len(p)} comprobante(s) · Bs {total:.2f}"
                    )
                else:
                    msgs.append(f"{rest_label(name)} — {date_str}: sin comprobantes")
            await update.message.reply_text(
                "\n".join(msgs) + "\n\nUsa `/comprobantes_dia " + date_str + " oasis` para ver detalle.",
                parse_mode="Markdown"
            )
            return

    pagos = db.get_payments_by_date(rid, date_str)

    if not pagos:
        await update.message.reply_text(
            f"📋 {rest_label(rname)}\n📅 {date_str}\n\n"
            f"Sin comprobantes registrados en esa fecha."
        )
        return

    icons = {
        "verified":      "✅",
        "wrong_account": "⚠️",
        "unreadable":    "❓",
        "pending":       "⏳",
    }

    manana = [p for p in pagos if (p["shift"] or "") == "manana"]
    noche  = [p for p in pagos if (p["shift"] or "") != "manana"]
    total  = sum(p["amount"] or 0 for p in pagos)

    lines = [
        f"📋 *Comprobantes — {rest_label(rname)}*",
        f"📅 {date_str}",
        f"💰 Total: *Bs {total:.2f}* · {len(pagos)} comprobante(s)\n",
    ]

    if manana:
        mt = sum(p["amount"] or 0 for p in manana)
        lines.append("☀️ *Turno Mañana (11:00–16:00):*")
        for p in manana:
            icon = icons.get(p["verification_status"], "⏳")
            t = (p["registered_at"] or "")[11:16]
            lines.append(
                f"  {icon} #{p['id']} {t}  Bs {p['amount']:.2f}  — {p['cashier_name']}"
            )
        lines.append(f"  _Subtotal: Bs {mt:.2f}_\n")

    if noche:
        nt = sum(p["amount"] or 0 for p in noche)
        lines.append("🌙 *Turno Noche (16:00–23:00):*")
        for p in noche:
            icon = icons.get(p["verification_status"], "⏳")
            t = (p["registered_at"] or "")[11:16]
            lines.append(
                f"  {icon} #{p['id']} {t}  Bs {p['amount']:.2f}  — {p['cashier_name']}"
            )
        lines.append(f"  _Subtotal: Bs {nt:.2f}_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # Enviar imágenes disponibles (máx. 20 para no spamear)
    img_pagos = [p for p in pagos if p["file_path"] or p["file_id"]]
    if not img_pagos:
        return

    await update.message.reply_text(
        f"📸 Enviando {len(img_pagos)} comprobante(s) con foto…"
    )

    sent = 0
    for p in img_pagos[:20]:
        icon    = icons.get(p["verification_status"], "⏳")
        turno   = "☀️" if (p["shift"] or "") == "manana" else "🌙"
        caption = (
            f"{icon} #{p['id']} {turno}  Bs {p['amount']:.2f}\n"
            f"👤 {p['cashier_name']}  ·  {(p['registered_at'] or '')[11:16]}"
        )
        try:
            local = os.path.join(COMPROBANTES_DIR, p["file_path"]) if p["file_path"] else None
            if local and os.path.exists(local):
                with open(local, "rb") as f:
                    await ctx.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=f,
                        caption=caption,
                    )
                sent += 1
            elif p["file_id"]:
                await ctx.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=p["file_id"],
                    caption=caption,
                )
                sent += 1
        except Exception as e:
            logger.warning(f"No se pudo enviar imagen #{p['id']}: {e}")

    if sent == 0:
        await update.message.reply_text(
            "⚠️ No se pudieron recuperar las imágenes (puede que los archivos se hayan movido)."
        )


# ── helpers ──────────────────────────────────────────────────────────────────

def _sort_key(t: str):
    """Orden natural: '1','2','10' → 1,2,10 en vez de '1','10','2'."""
    try:
        return (0, int(t), "")
    except ValueError:
        return (1, 0, t.lower())


# ── /mis_mesas ────────────────────────────────────────────────────────────────

@any_role
async def cmd_mis_mesas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /mis_mesas             → ver mesas asignadas hoy con estado de pedidos
    /mis_mesas 1 2 3 4     → asignar estas mesas para el turno
    /mis_mesas limpiar     → liberar todas mis mesas
    """
    rid         = ctx.user_data["restaurant_id"]
    rname       = ctx.user_data["restaurant_name"]
    mesero_id   = str(update.effective_user.id)
    mesero_name = ctx.user_data.get("username") or update.effective_user.full_name
    args        = ctx.args or []

    if not rid:
        await update.message.reply_text(
            "Primero dile al bot en qué restaurante estás:\n"
            "`/mi_restaurante oasis` o `/mi_restaurante dali`",
            parse_mode="Markdown"
        )
        return

    # /mis_mesas limpiar
    if args and args[0].lower() in ("limpiar", "clear", "borrar"):
        n = db.clear_mesero_tables(rid, mesero_id)
        await update.message.reply_text(
            f"✅ {n} mesa(s) liberadas en {rest_label(rname)}." if n
            else f"ℹ️ No tenías mesas asignadas en {rest_label(rname)} hoy."
        )
        return

    # /mis_mesas 1 2 3 → asignar
    if args:
        tables = [a.strip() for a in args if a.strip()]
        taken  = db.assign_tables(rid, mesero_id, mesero_name, tables)

        mesas_str = "\n".join(f"  🪑 Mesa {t}" for t in sorted(tables, key=_sort_key))
        msg = f"✅ *Mesas asignadas — {rest_label(rname)}*\n\n{mesas_str}"

        if taken:
            warn = "\n".join(f"  ⚠️ Mesa {t} (era de {n})" for t, n in taken)
            msg += f"\n\n{warn}"

        msg += f"\n\nUsa `/mesas` para ver el estado completo."
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # /mis_mesas sin args → mostrar estado
    mesas = db.get_mesero_tables(rid, mesero_id)
    if not mesas:
        await update.message.reply_text(
            f"🪑 *{rest_label(rname)}*\n\n"
            f"No tienes mesas asignadas hoy.\n\n"
            f"Para asignar: `/mis_mesas 1 2 3 4`",
            parse_mode="Markdown"
        )
        return

    orders = db.get_orders_by_mesero_today(rid, mesero_id)
    by_table: dict = {}
    for o in orders:
        if o["table_ref"]:
            by_table.setdefault(o["table_ref"], []).append(o)

    lines = [f"🪑 *Mis mesas — {rest_label(rname)}*\n"]
    for mesa in sorted(mesas, key=_sort_key):
        pedidos = by_table.get(mesa, [])
        if not pedidos:
            lines.append(f"  🟢 Mesa {mesa} — libre")
        else:
            pending = [o for o in pedidos if o["status"] == "pending"]
            ready   = [o for o in pedidos if o["status"] == "ready"]

            if ready:
                ids = " ".join(f"#{o['id']}" for o in ready)
                lines.append(f"  🔔 Mesa {mesa} — *¡LISTO!* {ids} → `/entregado N`")
            elif pending:
                lines.append(f"  ⏳ Mesa {mesa} — {len(pending)} en cocina")
            else:
                lines.append(f"  ✅ Mesa {mesa} — todo entregado")

    lines.append(f"\n_Cambiar: `/mis_mesas 1 2 3` · Liberar: `/mis_mesas limpiar`_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /mesas ────────────────────────────────────────────────────────────────────

def _build_mesas_view(rid: int, rname: str, solo_mesero_id: str | None = None) -> str:
    """
    Vista de mesas para un restaurante.
    solo_mesero_id=None → supervisora/cocina: todas las mesas agrupadas por mesero.
    solo_mesero_id=X    → mesero X: solo sus mesas.
    """
    assignments = db.get_all_table_assignments(rid)
    orders      = db.get_orders_today(rid)

    by_table: dict = {}
    for o in orders:
        if o["table_ref"]:
            by_table.setdefault(o["table_ref"], []).append(o)

    if solo_mesero_id:
        assignments = [a for a in assignments if a["mesero_id"] == solo_mesero_id]

    if not assignments:
        if solo_mesero_id:
            return (
                f"🪑 {rest_label(rname)}\n"
                f"No tienes mesas asignadas hoy.\n"
                f"Usa `/mis_mesas 1 2 3` para asignarte mesas."
            )
        return f"🪑 {rest_label(rname)}\nSin mesas asignadas hoy."

    # Agrupar asignaciones por mesero
    by_mesero: dict = {}
    for a in assignments:
        mid = a["mesero_id"]
        if mid not in by_mesero:
            by_mesero[mid] = {"name": a["mesero_name"], "tables": []}
        by_mesero[mid]["tables"].append(a["table_number"])

    lines = [f"🪑 *Mesas — {rest_label(rname)}*\n"]

    for mid, info in by_mesero.items():
        if not solo_mesero_id:
            lines.append(f"👤 *{info['name']}*")

        for mesa in sorted(info["tables"], key=_sort_key):
            pedidos = by_table.get(mesa, [])
            if not pedidos:
                lines.append(f"  🟢 Mesa {mesa} — libre")
            else:
                pending = [o for o in pedidos if o["status"] == "pending"]
                ready   = [o for o in pedidos if o["status"] == "ready"]

                if ready:
                    ids = " ".join(f"#{o['id']}" for o in ready)
                    lines.append(f"  🔔 Mesa {mesa} — *¡LISTO!* {ids}")
                elif pending:
                    lines.append(f"  ⏳ Mesa {mesa} — {len(pending)} en cocina")
                else:
                    lines.append(f"  ✅ Mesa {mesa} — todo entregado")

        if not solo_mesero_id:
            lines.append("")

    return "\n".join(lines).rstrip()


@require_role("mesero", "cashier", "kitchen_chief", "supervisor", "boss")
async def cmd_mesas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /mesas
    Mesero → sus mesas con estado de pedidos.
    Cocina / supervisora / boss → todas las mesas del restaurante agrupadas por mesero.
    """
    rid   = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    role  = ctx.user_data["role"]

    # Boss sin restaurante → ambos
    if role == "boss" and not rid:
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            msgs.append(_build_mesas_view(rest["id"], name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    solo = str(update.effective_user.id) if role == "mesero" else None
    await update.message.reply_text(_build_mesas_view(rid, rname, solo), parse_mode="Markdown")
