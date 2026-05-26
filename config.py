import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEB_URL = os.getenv("WEB_URL", "http://localhost:5000")
DB_PATH = os.getenv("DB_PATH", "restaurante.db")

# ── IDs de Telegram por rol y restaurante ──────────────────────────────────


def _parse_ids(env_key: str) -> set[str]:
    raw = os.getenv(env_key, "")
    return {x.strip() for x in raw.split(",") if x.strip()}


ADMIN_IDS            = _parse_ids("ADMIN_IDS")
OASIS_SUPERVISOR_IDS = _parse_ids("OASIS_SUPERVISOR_IDS")
DALI_SUPERVISOR_IDS  = _parse_ids("DALI_SUPERVISOR_IDS")
OASIS_CHIEF_IDS      = _parse_ids("OASIS_CHIEF_IDS")
DALI_CHIEF_IDS       = _parse_ids("DALI_CHIEF_IDS")
OASIS_CASHIER_IDS    = _parse_ids("OASIS_CASHIER_IDS")
DALI_CASHIER_IDS     = _parse_ids("DALI_CASHIER_IDS")


def get_role_and_restaurant(telegram_id: str) -> tuple[str, str] | tuple[None, None]:
    """Returns (role, restaurant_name) for a telegram_id, or (None, None)."""
    tid = str(telegram_id)
    if tid in ADMIN_IDS:
        return ("boss", None)
    if tid in OASIS_SUPERVISOR_IDS:
        return ("supervisor", "oasis")
    if tid in DALI_SUPERVISOR_IDS:
        return ("supervisor", "dali")
    if tid in OASIS_CHIEF_IDS:
        return ("kitchen_chief", "oasis")
    if tid in DALI_CHIEF_IDS:
        return ("kitchen_chief", "dali")
    if tid in OASIS_CASHIER_IDS:
        return ("cashier", "oasis")
    if tid in DALI_CASHIER_IDS:
        return ("cashier", "dali")
    return (None, None)


def all_ids_for_restaurant(restaurant_name: str) -> set[str]:
    """All known telegram IDs that belong to a restaurant."""
    if restaurant_name == "oasis":
        return OASIS_SUPERVISOR_IDS | OASIS_CHIEF_IDS | OASIS_CASHIER_IDS
    return DALI_SUPERVISOR_IDS | DALI_CHIEF_IDS | DALI_CASHIER_IDS


ALERT_LOW_THRESHOLD = 5

# ── Cuentas QR / bancarias de cada restaurante ──────────────────────────────
# Números contra los que se verifica el comprobante (sin espacios ni guiones)

def _norm_account(raw: str) -> str:
    """Normaliza un número de cuenta: solo dígitos y letras."""
    return "".join(c for c in raw if c.isalnum()).lower()


OASIS_ACCOUNT_RAW = os.getenv("OASIS_ACCOUNT_NUMBER", "")
DALI_ACCOUNT_RAW  = os.getenv("DALI_ACCOUNT_NUMBER", "")

OASIS_ACCOUNT = _norm_account(OASIS_ACCOUNT_RAW)
DALI_ACCOUNT  = _norm_account(DALI_ACCOUNT_RAW)


def get_restaurant_account(restaurant_name: str) -> str:
    """Returns the normalised account number for a restaurant."""
    return OASIS_ACCOUNT if restaurant_name == "oasis" else DALI_ACCOUNT


def verify_account(extracted: str, restaurant_name: str) -> str:
    """
    Returns 'verified', 'wrong_account', or 'unreadable'.
    Uses substring matching to handle partial reads.
    """
    if not extracted:
        return "unreadable"
    norm = _norm_account(extracted)
    expected = get_restaurant_account(restaurant_name)
    if not expected:
        return "pending"   # not configured yet
    if expected in norm or norm in expected:
        return "verified"
    return "wrong_account"
