"""Motor de sugerencias de refresco: temporada + rotación."""
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
import database as db
from handlers.roles import any_role, require_role, rest_label

# Frutas de temporada por mes (contexto Bolivia / América del Sur)
FRUTAS_POR_MES = {
    1:  ["Mango",       "Sandía",       "Papaya",      "Piña"],
    2:  ["Mango",       "Maracuyá",     "Papaya",      "Sandía"],
    3:  ["Maracuyá",    "Guayaba",      "Papaya",      "Naranja"],
    4:  ["Maracuyá",    "Naranja",      "Guayaba",     "Mandarina"],
    5:  ["Maracuyá",    "Mandarina",    "Durazno",     "Naranja"],
    6:  ["Durazno",     "Frutilla",     "Naranja",     "Mandarina"],
    7:  ["Frutilla",    "Durazno",      "Manzana",     "Naranja"],
    8:  ["Frutilla",    "Pera",         "Manzana",     "Durazno"],
    9:  ["Frutilla",    "Uva",          "Manzana",     "Pera"],
    10: ["Uva",         "Tuna",         "Manzana",     "Frutilla"],
    11: ["Chirimoya",   "Uva",          "Mango",       "Tuna"],
    12: ["Mango",       "Sandía",       "Piña",        "Chirimoya"],
}

# Plantillas de nombre de refresco para cada fruta
RECETAS = {
    "Mango":      ["Jugo de mango",     "Frappe de mango",    "Limonada de mango"],
    "Sandía":     ["Jugo de sandía",    "Agua de sandía",     "Frappe de sandía"],
    "Papaya":     ["Jugo de papaya",    "Batido de papaya",   "Jugo de papaya con naranja"],
    "Piña":       ["Jugo de piña",      "Agua de piña",       "Limonada de piña"],
    "Maracuyá":   ["Jugo de maracuyá",  "Frappe de maracuyá", "Limonada de maracuyá"],
    "Guayaba":    ["Jugo de guayaba",   "Refresco de guayaba","Batido de guayaba"],
    "Naranja":    ["Jugo de naranja",   "Limonada naranja",   "Naranjada natural"],
    "Mandarina":  ["Jugo de mandarina", "Refresco de mandarina", "Mandarina natural"],
    "Durazno":    ["Jugo de durazno",   "Néctar de durazno",  "Frappe de durazno"],
    "Frutilla":   ["Frappe de frutilla","Jugo de frutilla",   "Batido de frutilla"],
    "Manzana":    ["Jugo de manzana",   "Refresco de manzana","Agua de manzana"],
    "Pera":       ["Jugo de pera",      "Néctar de pera",     "Refresco de pera"],
    "Uva":        ["Jugo de uva",       "Refresco de uva",    "Chicha de uva"],
    "Tuna":       ["Jugo de tuna",      "Agua de tuna",       "Refresco de tuna"],
    "Chirimoya":  ["Batido de chirimoya","Jugo de chirimoya", "Frappe de chirimoya"],
}


def sugerir_refresco(restaurant_id: int) -> dict:
    """
    Retorna el mejor refresco sugerido para hoy con su justificación.
    Prioriza: en temporada + no usado en los últimos 7 días.
    """
    mes = datetime.now().month
    frutas_temporada = FRUTAS_POR_MES.get(mes, ["Maracuyá", "Naranja"])

    # Bebidas usadas recientemente (últimos 14 días)
    recientes = db.get_recent_drinks(restaurant_id, days=14)
    nombres_recientes = {r["drink_name"].lower() for r in recientes}
    ultimo_usado = {r["drink_name"].lower(): r["last_used"] for r in recientes}

    candidatos = []

    for fruta in frutas_temporada:
        recetas = RECETAS.get(fruta, [f"Jugo de {fruta.lower()}"])
        for receta in recetas:
            nombre_lower = receta.lower()
            # Score: mayor = mejor candidato
            score = 0
            if nombre_lower not in nombres_recientes:
                score += 100          # No usado en 2 semanas → prioritario
            else:
                dias_desde = _dias_desde(ultimo_usado.get(nombre_lower, ""))
                score += min(dias_desde * 5, 80)  # Más días sin usar = mejor score

            candidatos.append({
                "nombre": receta,
                "fruta": fruta,
                "score": score,
                "en_temporada": True,
                "dias_sin_usar": _dias_desde(ultimo_usado.get(nombre_lower, ""))
            })

    if not candidatos:
        return {"nombre": "Limonada natural", "fruta": "Limón",
                "razon": "Clásico siempre disponible", "score": 0}

    candidatos.sort(key=lambda x: x["score"], reverse=True)
    top = candidatos[0]

    razon_parts = [f"Fruta de temporada en {_nombre_mes(mes)}"]
    if top["dias_sin_usar"] >= 99:
        razon_parts.append("no se ha servido recientemente")
    else:
        razon_parts.append(f"última vez hace {top['dias_sin_usar']} días")

    top["razon"] = " · ".join(razon_parts)
    top["alternativas"] = [c["nombre"] for c in candidatos[1:4]]
    top["frutas_temporada"] = frutas_temporada
    return top


def _dias_desde(fecha_str: str) -> int:
    if not fecha_str:
        return 999
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
        return (datetime.now() - fecha).days
    except Exception:
        return 999


def _nombre_mes(mes: int) -> str:
    meses = ["","enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    return meses[mes]


# ── Comandos del bot ────────────────────────────────────────────────────────

@any_role
async def cmd_sugerir_refresco(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            sug = sugerir_refresco(rest["id"])
            msgs.append(_format_suggestion(sug, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    rid = ctx.user_data["restaurant_id"]
    sug = sugerir_refresco(rid)
    await update.message.reply_text(_format_suggestion(sug, rname), parse_mode="Markdown")


def _format_suggestion(sug: dict, rname: str) -> str:
    alts = "\n".join(f"  • {a}" for a in sug.get("alternativas", []))
    temporada = ", ".join(sug.get("frutas_temporada", []))
    return (
        f"{rest_label(rname)} — Sugerencia de refresco\n\n"
        f"⭐ *{sug['nombre']}*\n"
        f"🍓 Fruta: {sug.get('fruta','—')}\n"
        f"📅 {sug.get('razon','')}\n\n"
        f"Alternativas:\n{alts}\n\n"
        f"🌿 Frutas de temporada: {temporada}\n\n"
        f"Para usar esta sugerencia en el menú:\n"
        f"`/definir_menu <sopa> | <plato> | {sug['nombre']} | <precio> | <cantidad>`"
    )


@require_role("kitchen_chief", "supervisor", "boss")
async def cmd_nueva_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Uso: /nueva_promo <nombre> | <precio> | [descripción]
    Ejemplo: /nueva_promo Frappe de frutas | 2x35 Bs | Lunes de promo
    """
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    args = " ".join(ctx.args) if ctx.args else ""
    parts = [p.strip() for p in args.split("|")]

    if len(parts) < 2:
        await update.message.reply_text(
            "📋 *Formato:*\n`/nueva_promo Nombre | Precio | Descripción`\n\n"
            "Ejemplo:\n`/nueva_promo Frappe de frutas | 2x35 Bs | Lunes de promo`",
            parse_mode="Markdown"
        )
        return

    name = parts[0]
    price = parts[1]
    desc = parts[2] if len(parts) > 2 else ""

    pid = db.add_promo(rid, name, price, desc, source="manual")
    await update.message.reply_text(
        f"✅ Promo agregada en {rest_label(rname)}\n\n"
        f"🏷 *{name}* — {price}\n"
        f"📝 {desc}\n"
        f"ID: `{pid}`",
        parse_mode="Markdown"
    )


@any_role
async def cmd_ver_promos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    role = ctx.user_data["role"]
    rname = ctx.user_data["restaurant_name"]

    if role == "boss":
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            promos = db.get_active_promos(rest["id"])
            msgs.append(_format_promos(promos, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    rid = ctx.user_data["restaurant_id"]
    promos = db.get_active_promos(rid)
    await update.message.reply_text(_format_promos(promos, rname), parse_mode="Markdown")


def _format_promos(promos: list, rname: str) -> str:
    label = rest_label(rname)
    if not promos:
        return f"{label}\n❌ Sin promos activas."
    lines = [f"{label} — Promos activas\n"]
    for p in promos:
        src = "🌐 FB" if p["source"] == "facebook" else "✍️ Manual"
        lines.append(f"🏷 *{p['name']}* — {p['price']} {src}")
        if p["description"]:
            lines.append(f"   {p['description']}")
    return "\n".join(lines)
