from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import database as db
import config

ROLE_LABELS = {
    "boss": "Dueño",
    "supervisor": "Supervisora",
    "kitchen_chief": "Jefe de Cocina",
    "cashier": "Cajero/a",
}


def _get_user_context(telegram_id: str) -> tuple[str, str, int | None]:
    """Returns (role, restaurant_name, restaurant_id). Reads from DB first, falls back to config."""
    user = db.get_user(str(telegram_id))
    if user:
        rest = db.get_restaurant_by_id(user["restaurant_id"]) if user["restaurant_id"] else None
        return user["role"], (rest["name"] if rest else None), user["restaurant_id"]

    role, rest_name = config.get_role_and_restaurant(str(telegram_id))
    if role is None:
        return None, None, None

    # Auto-register on first encounter
    rest = db.get_restaurant(rest_name) if rest_name else None
    rid = rest["id"] if rest else None
    # We don't have the name here; it'll be filled in /start
    return role, rest_name, rid


def require_role(*allowed_roles):
    """Decorator: only allows users whose role is in allowed_roles."""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            uid = str(update.effective_user.id)
            role, rest_name, rid = _get_user_context(uid)
            if role is None:
                await update.message.reply_text(
                    "⛔ No tienes acceso a este bot.\n"
                    "Contacta al administrador para que te registre."
                )
                return
            if role not in allowed_roles:
                labels = " / ".join(ROLE_LABELS.get(r, r) for r in allowed_roles)
                await update.message.reply_text(
                    f"⛔ Esta acción es solo para: *{labels}*.",
                    parse_mode="Markdown"
                )
                return
            ctx.user_data["role"] = role
            ctx.user_data["restaurant_name"] = rest_name
            ctx.user_data["restaurant_id"] = rid
            return await func(update, ctx, *args, **kwargs)
        return wrapper
    return decorator


def any_role(func):
    """Decorator: allows any registered user."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = str(update.effective_user.id)
        role, rest_name, rid = _get_user_context(uid)
        if role is None:
            await update.message.reply_text(
                "⛔ No tienes acceso a este bot.\n"
                "Contacta al administrador para que te registre."
            )
            return
        ctx.user_data["role"] = role
        ctx.user_data["restaurant_name"] = rest_name
        ctx.user_data["restaurant_id"] = rid
        return await func(update, ctx, *args, **kwargs)
    return wrapper


def inject_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fill ctx.user_data with role/restaurant without permission check."""
    uid = str(update.effective_user.id)
    role, rest_name, rid = _get_user_context(uid)
    ctx.user_data["role"] = role
    ctx.user_data["restaurant_name"] = rest_name
    ctx.user_data["restaurant_id"] = rid
    return role, rest_name, rid


def rest_label(name: str | None) -> str:
    if not name:
        return ""
    return "🌴 Oasis" if name == "oasis" else "🎨 Dali"
