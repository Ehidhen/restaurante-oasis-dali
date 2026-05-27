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
    "mesero": "Mesero/a",
}


def _get_user_context(telegram_id: str) -> tuple[str, str, int | None]:
    """Returns (role, restaurant_name, restaurant_id). Reads from DB first, falls back to config.
    For meseros: uses current_restaurant_id if set (allows switching between restaurants)."""
    user = db.get_user(str(telegram_id))
    if user:
        role = user["role"]
        # Meseros can switch restaurants — use current_restaurant_id if set
        active_rid = None
        if role == "mesero":
            try:
                active_rid = user["current_restaurant_id"]
            except (IndexError, KeyError):
                active_rid = None
            if not active_rid:
                active_rid = user["restaurant_id"]
        else:
            active_rid = user["restaurant_id"]

        rest = db.get_restaurant_by_id(active_rid) if active_rid else None
        return role, (rest["name"] if rest else None), (rest["id"] if rest else None)

    role, rest_name = config.get_role_and_restaurant(str(telegram_id))
    if role is None:
        return None, None, None

    # Auto-register on first encounter
    rest = db.get_restaurant(rest_name) if rest_name else None
    rid = rest["id"] if rest else None
    return role, rest_name, rid


def require_role(*allowed_roles):
    """Decorator: only allows users whose role is in allowed_roles.

    For the 'boss' role with no assigned restaurant (rid=None), the
    decorator inspects ctx.args for an optional leading 'oasis'/'dali'
    token and routes the command to that restaurant automatically,
    removing the token so the command handler sees clean arguments.
    Example: /checklist dali  →  cmd_checklist runs as if boss is in Dali.
    """
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

            # Boss without a fixed restaurant: try to resolve from first arg
            if role == "boss" and rid is None:
                first = (ctx.args[0].lower().strip() if ctx.args else "")
                if first in ("oasis", "dali"):
                    rest_override = db.get_restaurant(first)
                    if rest_override:
                        rest_name = first
                        rid       = rest_override["id"]
                        ctx.args  = list(ctx.args[1:])  # consume the token

            ctx.user_data["role"]            = role
            ctx.user_data["restaurant_name"] = rest_name
            ctx.user_data["restaurant_id"]   = rid
            ctx.user_data["username"] = (
                update.effective_user.full_name
                or update.effective_user.first_name
                or "Usuario"
            )
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
        ctx.user_data["username"] = (
            update.effective_user.full_name
            or update.effective_user.first_name
            or "Usuario"
        )
        return await func(update, ctx, *args, **kwargs)
    return wrapper


def inject_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fill ctx.user_data with role/restaurant without permission check."""
    uid = str(update.effective_user.id)
    role, rest_name, rid = _get_user_context(uid)
    ctx.user_data["role"] = role
    ctx.user_data["restaurant_name"] = rest_name
    ctx.user_data["restaurant_id"] = rid
    ctx.user_data["username"] = (
        update.effective_user.full_name
        or update.effective_user.first_name
        or "Usuario"
    )
    return role, rest_name, rid


def rest_label(name: str | None) -> str:
    if not name:
        return ""
    return "🌴 Oasis" if name == "oasis" else "🎨 Dali"
