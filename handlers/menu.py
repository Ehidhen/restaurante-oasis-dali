from telegram import Update
from telegram.ext import ContextTypes
import database as db
from handlers.roles import any_role, require_role, rest_label


@any_role
async def cmd_menu_hoy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    if ctx.user_data["role"] == "boss":
        # Boss sees both restaurants
        msgs = []
        for name in ["oasis", "dali"]:
            rest = db.get_restaurant(name)
            menu = db.get_menu(rest["id"])
            msgs.append(_format_menu(menu, name))
        await update.message.reply_text("\n\n".join(msgs), parse_mode="Markdown")
        return

    menu = db.get_menu(rid)
    await update.message.reply_text(_format_menu(menu, rname), parse_mode="Markdown")


def _format_menu(menu, rname: str) -> str:
    label = rest_label(rname)
    if not menu:
        return f"{label}\n❌ No hay menú definido para hoy."
    extras_note = ""
    qty = menu["current_qty"]
    estado = "✅ Disponible" if qty > 0 else "❌ AGOTADO"
    return (
        f"{label} — Menú de hoy\n"
        f"🍲 Sopa: {menu['soup'] or '—'}\n"
        f"🍽 Plato: {menu['main_dish'] or '—'}\n"
        f"🥤 Refresco: {menu['drink'] or '—'}\n"
        f"💰 Precio: Bs {menu['price']:.2f}\n"
        f"🔢 Almuerzos: *{qty}* restantes\n"
        f"Estado: {estado}"
    )


@require_role("kitchen_chief", "boss")
async def cmd_definir_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Uso: /definir_menu <sopa> | <plato> | <refresco> | <precio> | <cantidad>
    Ejemplo: /definir_menu Sopa de pollo | Arroz con carne | Jugo de mora | 8.50 | 60
    """
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    args = " ".join(ctx.args) if ctx.args else ""

    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 5:
        await update.message.reply_text(
            "📋 *Formato:*\n"
            "`/definir_menu Sopa | Plato | Refresco | Precio | Cantidad`\n\n"
            "Ejemplo:\n"
            "`/definir_menu Sopa de pollo | Arroz con carne | Jugo de mora | 8.50 | 60`",
            parse_mode="Markdown"
        )
        return

    soup, main_dish, drink = parts[0], parts[1], parts[2]
    try:
        price = float(parts[3].replace(",", "."))
        initial_qty = int(parts[4])
    except ValueError:
        await update.message.reply_text("❌ El precio debe ser un número y la cantidad un entero.")
        return

    user = ctx.user_data.get("username") or update.effective_user.full_name
    db.set_menu(rid, soup, main_dish, drink, price, initial_qty, updated_by=user)
    await update.message.reply_text(
        f"✅ Menú guardado para {rest_label(rname)}\n\n"
        f"🍲 Sopa: {soup}\n"
        f"🍽 Plato: {main_dish}\n"
        f"🥤 Refresco: {drink}\n"
        f"💰 Precio: Bs {price:.2f}\n"
        f"🔢 Cantidad inicial: {initial_qty}",
        parse_mode="Markdown"
    )


@require_role("kitchen_chief", "boss")
async def cmd_agregar_extra(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Uso: /agregar_extra <nombre> | <precio>
    """
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]
    args = " ".join(ctx.args) if ctx.args else ""
    parts = [p.strip() for p in args.split("|")]

    if len(parts) < 2:
        await update.message.reply_text(
            "📋 *Formato:*\n`/agregar_extra Nombre del plato | Precio`\n"
            "Ejemplo: `/agregar_extra Pollo a la plancha | 5.00`",
            parse_mode="Markdown"
        )
        return

    name_dish = parts[0]
    try:
        price = float(parts[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ El precio debe ser un número.")
        return

    db.add_extra_dish(rid, name_dish, price)
    await update.message.reply_text(
        f"✅ Plato extra agregado en {rest_label(rname)}\n"
        f"🍴 {name_dish} — Bs {price:.2f}"
    )


@require_role("kitchen_chief", "boss")
async def cmd_precio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Uso: /precio 8.50"""
    rid = ctx.user_data["restaurant_id"]
    rname = ctx.user_data["restaurant_name"]

    if not ctx.args:
        menu = db.get_menu(rid)
        current = f"Bs {menu['price']:.2f}" if menu else "no definido"
        await update.message.reply_text(
            f"💰 Precio actual en {rest_label(rname)}: {current}\n"
            f"Para cambiar: `/precio 8.50`",
            parse_mode="Markdown"
        )
        return

    try:
        price = float(ctx.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Indica un precio válido. Ej: `/precio 8.50`",
                                        parse_mode="Markdown")
        return

    menu = db.get_menu(rid)
    if not menu:
        await update.message.reply_text("❌ Primero define el menú con /definir_menu")
        return

    db.set_menu_price(rid, price)
    await update.message.reply_text(
        f"✅ Precio actualizado en {rest_label(rname)}: *Bs {price:.2f}*",
        parse_mode="Markdown"
    )
