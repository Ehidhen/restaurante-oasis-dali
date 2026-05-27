from telegram import Update
from telegram.ext import ContextTypes
import database as db
from handlers.roles import any_role, require_role, rest_label


@any_role
async def cmd_resumen_hoy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            summary = db.get_daily_summary(rest["id"])
            msgs.append(_format_daily(summary, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    rid = ctx.user_data["restaurant_id"]
    summary = db.get_daily_summary(rid)
    await update.message.reply_text(_format_daily(summary, rname), parse_mode="Markdown")


def _format_daily(summary: dict, rname: str) -> str:
    alm_qty, alm_tot = summary.get("almuerzo", (0, 0.0))
    ext_qty, ext_tot = summary.get("extra", (0, 0.0))
    ref_qty, ref_tot = summary.get("refresco", (0, 0.0))
    total = summary.get("total", 0.0)

    return (
        f"{rest_label(rname)} — Resumen de hoy\n"
        f"🍽 Almuerzos: {alm_qty} — Bs {alm_tot:.2f}\n"
        f"🍴 Extras: {ext_qty} — Bs {ext_tot:.2f}\n"
        f"🥤 Refrescos: {ref_qty} — Bs {ref_tot:.2f}\n"
        f"────────────────\n"
        f"💰 *Total: Bs {total:.2f}*"
    )


@any_role
async def cmd_resumen_semana(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            rows = db.get_weekly_summary(rest["id"])
            msgs.append(_format_weekly(rows, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    rid = ctx.user_data["restaurant_id"]
    rows = db.get_weekly_summary(rid)
    await update.message.reply_text(_format_weekly(rows, rname), parse_mode="Markdown")


def _format_weekly(rows: list, rname: str) -> str:
    label = rest_label(rname)
    if not rows:
        return f"{label}\n❌ Sin ventas esta semana."

    lines = [f"{label} — Resumen semanal\n"]
    grand_total = 0.0
    grand_qty = 0
    for row in rows:
        lines.append(f"📅 {row['date']}: {row['qty']} ventas — Bs {row['total']:.2f}")
        grand_total += row["total"]
        grand_qty += row["qty"]

    lines.append(f"────────────────")
    lines.append(f"📊 Total: {grand_qty} ventas — *Bs {grand_total:.2f}*")
    return "\n".join(lines)


@require_role("boss")
async def cmd_comparar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    oasis = db.get_restaurant("oasis")
    dali = db.get_restaurant("dali")
    o_sum = db.get_daily_summary(oasis["id"])
    d_sum = db.get_daily_summary(dali["id"])

    o_total = o_sum.get("total", 0.0)
    d_total = d_sum.get("total", 0.0)
    o_alm = o_sum.get("almuerzo", (0, 0.0))[0]
    d_alm = d_sum.get("almuerzo", (0, 0.0))[0]
    o_qty_now = db.get_current_qty(oasis["id"])
    d_qty_now = db.get_current_qty(dali["id"])

    winner = "🌴 Oasis" if o_total >= d_total else "🎨 Dali"

    msg = (
        f"📊 *Comparativa de hoy*\n\n"
        f"{'─' * 30}\n"
        f"🌴 *Oasis*\n"
        f"  Almuerzos vendidos: {o_alm}\n"
        f"  Ingresos: Bs {o_total:.2f}\n"
        f"  Quedan: {o_qty_now}\n\n"
        f"🎨 *Dali*\n"
        f"  Almuerzos vendidos: {d_alm}\n"
        f"  Ingresos: Bs {d_total:.2f}\n"
        f"  Quedan: {d_qty_now}\n"
        f"{'─' * 30}\n"
        f"🏆 Líder hoy: {winner}\n"
        f"💰 Total ambos: Bs {o_total + d_total:.2f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
