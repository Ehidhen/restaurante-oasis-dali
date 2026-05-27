import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "restaurante.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id          TEXT UNIQUE NOT NULL,
            name                 TEXT NOT NULL,
            role                 TEXT NOT NULL,
            restaurant_id        INTEGER REFERENCES restaurants(id),
            current_restaurant_id INTEGER REFERENCES restaurants(id)
        );

        CREATE TABLE IF NOT EXISTS daily_menu (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            date          TEXT NOT NULL,
            soup          TEXT,
            main_dish     TEXT,
            drink         TEXT,
            price         REAL DEFAULT 0,
            initial_qty   INTEGER DEFAULT 0,
            current_qty   INTEGER DEFAULT 0,
            updated_by    TEXT DEFAULT 'Sistema',
            updated_at    TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(restaurant_id, date)
        );

        CREATE TABLE IF NOT EXISTS extra_dishes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            name          TEXT NOT NULL,
            price         REAL NOT NULL,
            active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sales (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            date          TEXT NOT NULL,
            type          TEXT NOT NULL,
            quantity      INTEGER NOT NULL DEFAULT 1,
            amount        REAL NOT NULL,
            cashier_id    TEXT,
            created_at    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS inventory_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            name          TEXT NOT NULL,
            unit          TEXT DEFAULT 'unidad',
            category      TEXT DEFAULT 'otro'
        );

        CREATE TABLE IF NOT EXISTS shortage_list (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id),
            item_id         INTEGER REFERENCES inventory_items(id),
            item_name       TEXT NOT NULL,
            quantity_needed TEXT NOT NULL,
            date            TEXT NOT NULL,
            status          TEXT DEFAULT 'pending',
            updated_by      TEXT DEFAULT 'Sistema',
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS social_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT DEFAULT 'facebook',
            post_id     TEXT UNIQUE,
            content     TEXT,
            image_url   TEXT,
            post_url    TEXT,
            detected_at TEXT DEFAULT (datetime('now','localtime')),
            notified    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS drink_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            drink_name    TEXT NOT NULL,
            date          TEXT NOT NULL,
            suggested     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS promos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            name          TEXT NOT NULL,
            price         TEXT,
            description   TEXT,
            source        TEXT DEFAULT 'manual',
            image_url     TEXT,
            active        INTEGER DEFAULT 1,
            created_at    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS transfers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            from_restaurant INTEGER NOT NULL REFERENCES restaurants(id),
            to_restaurant   INTEGER NOT NULL REFERENCES restaurants(id),
            quantity        INTEGER NOT NULL,
            status          TEXT DEFAULT 'requested',
            requested_by    TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id       INTEGER NOT NULL REFERENCES restaurants(id),
            cashier_name        TEXT NOT NULL,
            amount              REAL DEFAULT 0,
            description         TEXT DEFAULT '',
            file_id             TEXT NOT NULL,
            file_path           TEXT DEFAULT '',
            shift               TEXT DEFAULT '',
            extracted_account   TEXT DEFAULT '',
            extracted_amount    REAL DEFAULT 0,
            verification_status TEXT DEFAULT 'pending',
            verification_note   TEXT DEFAULT '',
            registered_at       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id),
            mesero_id       TEXT NOT NULL,
            mesero_name     TEXT NOT NULL,
            table_ref       TEXT DEFAULT '',
            items           TEXT NOT NULL,
            notes           TEXT DEFAULT '',
            status          TEXT DEFAULT 'pending',
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            ready_at        TEXT DEFAULT NULL,
            served_at       TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS table_assignments (
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            mesero_id     TEXT NOT NULL,
            mesero_name   TEXT NOT NULL,
            table_number  TEXT NOT NULL,
            date          TEXT NOT NULL,
            PRIMARY KEY (restaurant_id, table_number, date)
        );
    """)

    # Seed restaurantes
    c.execute("INSERT OR IGNORE INTO restaurants (name) VALUES ('oasis')")
    c.execute("INSERT OR IGNORE INTO restaurants (name) VALUES ('dali')")

    # Migrate users table — add current_restaurant_id if upgrading from older schema
    _existing_users = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
    if "current_restaurant_id" not in _existing_users:
        c.execute("ALTER TABLE users ADD COLUMN current_restaurant_id INTEGER REFERENCES restaurants(id)")

    # Migrate payments table — add new columns if upgrading from older schema
    _existing = {row[1] for row in c.execute("PRAGMA table_info(payments)").fetchall()}
    for col, defn in [
        ("shift",               "TEXT DEFAULT ''"),
        ("extracted_account",   "TEXT DEFAULT ''"),
        ("extracted_amount",    "REAL DEFAULT 0"),
        ("verification_status", "TEXT DEFAULT 'pending'"),
        ("verification_note",   "TEXT DEFAULT ''"),
    ]:
        if col not in _existing:
            c.execute(f"ALTER TABLE payments ADD COLUMN {col} {defn}")

    conn.commit()
    conn.close()


# ── Helpers de restaurante ──────────────────────────────────────────────────

def get_restaurant(name: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM restaurants WHERE name = ?", (name.lower(),)
        ).fetchone()


def get_restaurant_by_id(rid: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM restaurants WHERE id = ?", (rid,)
        ).fetchone()


def other_restaurant_id(rid: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM restaurants WHERE id != ?", (rid,)
        ).fetchone()
        return row["id"] if row else rid


# ── Usuarios ────────────────────────────────────────────────────────────────

def get_user(telegram_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (str(telegram_id),)
        ).fetchone()


def upsert_user(telegram_id: str, name: str, role: str, restaurant_id: int,
                current_restaurant_id: int | None = None):
    curr_rid = current_restaurant_id if current_restaurant_id is not None else restaurant_id
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, name, role, restaurant_id, current_restaurant_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name=excluded.name, role=excluded.role,
                restaurant_id=excluded.restaurant_id
        """, (str(telegram_id), name, role, restaurant_id, curr_rid))
        conn.commit()


def set_user_restaurant(telegram_id: str, restaurant_id: int) -> bool:
    """Update current_restaurant_id (active working location) for a user.
    Returns True if the user record existed and was updated."""
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE users SET current_restaurant_id = ?
            WHERE telegram_id = ?
        """, (restaurant_id, str(telegram_id)))
        conn.commit()
        return cur.rowcount > 0


def get_users_by_role_and_restaurant(role: str, restaurant_id: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE role = ? AND restaurant_id = ?",
            (role, restaurant_id)
        ).fetchall()


def get_all_users_by_restaurant(restaurant_id: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE restaurant_id = ?", (restaurant_id,)
        ).fetchall()


# ── Menú del día ────────────────────────────────────────────────────────────

def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_menu(restaurant_id: int, date: str | None = None) -> sqlite3.Row | None:
    date = date or today()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM daily_menu WHERE restaurant_id = ? AND date = ?",
            (restaurant_id, date)
        ).fetchone()


def set_menu(restaurant_id: int, soup: str, main_dish: str, drink: str,
             price: float, initial_qty: int, updated_by: str = "Sistema"):
    date = today()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO daily_menu
                (restaurant_id, date, soup, main_dish, drink, price, initial_qty, current_qty, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(restaurant_id, date) DO UPDATE SET
                soup=excluded.soup, main_dish=excluded.main_dish,
                drink=excluded.drink, price=excluded.price,
                initial_qty=excluded.initial_qty, current_qty=excluded.current_qty,
                updated_by=excluded.updated_by, updated_at=excluded.updated_at
        """, (restaurant_id, date, soup, main_dish, drink, price, initial_qty, initial_qty, updated_by, now))
        conn.commit()


def set_menu_price(restaurant_id: int, price: float):
    date = today()
    with get_conn() as conn:
        conn.execute(
            "UPDATE daily_menu SET price = ? WHERE restaurant_id = ? AND date = ?",
            (price, restaurant_id, date)
        )
        conn.commit()


def get_current_qty(restaurant_id: int) -> int:
    menu = get_menu(restaurant_id)
    return menu["current_qty"] if menu else 0


def adjust_qty(restaurant_id: int, delta: int) -> int:
    """Adds delta (can be negative) to current_qty. Returns new qty."""
    date = today()
    with get_conn() as conn:
        conn.execute("""
            UPDATE daily_menu
            SET current_qty = MAX(0, current_qty + ?)
            WHERE restaurant_id = ? AND date = ?
        """, (delta, restaurant_id, date))
        conn.commit()
        row = conn.execute(
            "SELECT current_qty FROM daily_menu WHERE restaurant_id = ? AND date = ?",
            (restaurant_id, date)
        ).fetchone()
        return row["current_qty"] if row else 0


def set_qty(restaurant_id: int, qty: int) -> int:
    date = today()
    with get_conn() as conn:
        conn.execute("""
            UPDATE daily_menu SET current_qty = ?
            WHERE restaurant_id = ? AND date = ?
        """, (max(0, qty), restaurant_id, date))
        conn.commit()
    return max(0, qty)


# ── Platos extra ────────────────────────────────────────────────────────────

def add_extra_dish(restaurant_id: int, name: str, price: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO extra_dishes (restaurant_id, name, price) VALUES (?, ?, ?)",
            (restaurant_id, name, price)
        )
        conn.commit()


def get_extra_dishes(restaurant_id: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM extra_dishes WHERE restaurant_id = ? AND active = 1",
            (restaurant_id,)
        ).fetchall()


# ── Ventas ──────────────────────────────────────────────────────────────────

def register_sale(restaurant_id: int, sale_type: str, quantity: int,
                  amount: float, cashier_id: str):
    date = today()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (restaurant_id, date, sale_type, quantity, amount, str(cashier_id)))
        conn.commit()


def get_daily_sales(restaurant_id: int, date: str | None = None) -> list:
    date = date or today()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sales WHERE restaurant_id = ? AND date = ? ORDER BY created_at",
            (restaurant_id, date)
        ).fetchall()


def get_daily_summary(restaurant_id: int, date: str | None = None) -> dict:
    date = date or today()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT type, SUM(quantity) as qty, SUM(amount) as total
            FROM sales WHERE restaurant_id = ? AND date = ?
            GROUP BY type
        """, (restaurant_id, date)).fetchall()
    result = {"almuerzo": (0, 0.0), "extra": (0, 0.0), "refresco": (0, 0.0), "total": 0.0}
    for r in rows:
        result[r["type"]] = (r["qty"], r["total"])
        result["total"] += r["total"]
    return result


def get_weekly_summary(restaurant_id: int) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT date, SUM(quantity) as qty, SUM(amount) as total
            FROM sales WHERE restaurant_id = ?
              AND date >= date('now', '-6 days', 'localtime')
            GROUP BY date ORDER BY date DESC
        """, (restaurant_id,)).fetchall()


# ── Faltantes ───────────────────────────────────────────────────────────────

def add_shortage(restaurant_id: int, item_name: str, quantity_needed: str,
                 updated_by: str = "Sistema"):
    date = today()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO shortage_list (restaurant_id, item_name, quantity_needed, date, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (restaurant_id, item_name, quantity_needed, date, updated_by, now))
        conn.commit()


def get_shortages(restaurant_id: int, status: str = "pending") -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM shortage_list
            WHERE restaurant_id = ? AND status = ?
            ORDER BY id DESC
        """, (restaurant_id, status)).fetchall()


def mark_shortage_bought(restaurant_id: int, item_name: str,
                         updated_by: str = "Sistema") -> bool:
    """Marca como comprado SOLO en los faltantes de HOY."""
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date = today()
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE shortage_list SET status = 'bought', updated_by = ?, updated_at = ?
            WHERE restaurant_id = ? AND item_name LIKE ? AND status = 'pending'
              AND date = ?
        """, (updated_by, now, restaurant_id, f"%{item_name}%", date))
        conn.commit()
        return cur.rowcount > 0


def get_all_shortages_today(restaurant_id: int) -> list:
    date = today()
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM shortage_list
            WHERE restaurant_id = ? AND date = ?
            ORDER BY status, id
        """, (restaurant_id, date)).fetchall()


def get_shortages_by_date(restaurant_id: int, date: str,
                           status: str | None = None) -> list:
    """Returns shortage_list entries for a given date (YYYY-MM-DD).
    Optionally filter by status ('pending' or 'bought')."""
    with get_conn() as conn:
        if status:
            return conn.execute("""
                SELECT * FROM shortage_list
                WHERE restaurant_id = ? AND date = ? AND status = ?
                ORDER BY id
            """, (restaurant_id, date, status)).fetchall()
        return conn.execute("""
            SELECT * FROM shortage_list
            WHERE restaurant_id = ? AND date = ?
            ORDER BY status, id
        """, (restaurant_id, date)).fetchall()


# ── Transferencias ──────────────────────────────────────────────────────────

def create_transfer(from_rid: int, to_rid: int, quantity: int,
                    requested_by: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO transfers (from_restaurant, to_restaurant, quantity, requested_by)
            VALUES (?, ?, ?, ?)
        """, (from_rid, to_rid, quantity, str(requested_by)))
        conn.commit()
        return cur.lastrowid


def update_transfer_status(transfer_id: int, status: str):
    with get_conn() as conn:
        conn.execute("""
            UPDATE transfers SET status = ?, updated_at = datetime('now','localtime')
            WHERE id = ?
        """, (status, transfer_id))
        conn.commit()


def get_pending_transfer(restaurant_id: int) -> sqlite3.Row | None:
    """Returns the latest non-received transfer involving this restaurant."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM transfers
            WHERE (from_restaurant = ? OR to_restaurant = ?)
              AND status != 'received'
            ORDER BY created_at DESC LIMIT 1
        """, (restaurant_id, restaurant_id)).fetchone()


def get_today_transfers(restaurant_id: int) -> list:
    date = today()
    with get_conn() as conn:
        return conn.execute("""
            SELECT t.*, r1.name as from_name, r2.name as to_name
            FROM transfers t
            JOIN restaurants r1 ON r1.id = t.from_restaurant
            JOIN restaurants r2 ON r2.id = t.to_restaurant
            WHERE (t.from_restaurant = ? OR t.to_restaurant = ?)
              AND date(t.created_at) = ?
            ORDER BY t.created_at DESC
        """, (restaurant_id, restaurant_id, date)).fetchall()


def get_all_today_transfers() -> list:
    date = today()
    with get_conn() as conn:
        return conn.execute("""
            SELECT t.*, r1.name as from_name, r2.name as to_name
            FROM transfers t
            JOIN restaurants r1 ON r1.id = t.from_restaurant
            JOIN restaurants r2 ON r2.id = t.to_restaurant
            WHERE date(t.created_at) = ?
            ORDER BY t.created_at DESC
        """, (date,)).fetchall()


# ── Social posts ────────────────────────────────────────────────────────────

def save_social_post(post_id: str, content: str, image_url: str,
                     post_url: str, platform: str = "facebook") -> bool:
    """Returns True if it's a new post (not seen before)."""
    with get_conn() as conn:
        try:
            conn.execute("""
                INSERT INTO social_posts (platform, post_id, content, image_url, post_url)
                VALUES (?, ?, ?, ?, ?)
            """, (platform, post_id, content, image_url, post_url))
            conn.commit()
            return True
        except Exception:
            return False


def get_unnotified_posts() -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM social_posts WHERE notified = 0 ORDER BY detected_at DESC"
        ).fetchall()


def mark_post_notified(post_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE social_posts SET notified = 1 WHERE post_id = ?", (post_id,)
        )
        conn.commit()


def get_latest_social_posts(limit: int = 3) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM social_posts ORDER BY detected_at DESC LIMIT ?", (limit,)
        ).fetchall()


# ── Drink history & suggestions ─────────────────────────────────────────────

def log_drink(restaurant_id: int, drink_name: str, suggested: bool = False):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO drink_history (restaurant_id, drink_name, date, suggested)
            VALUES (?, ?, ?, ?)
        """, (restaurant_id, drink_name, today(), 1 if suggested else 0))
        conn.commit()


def get_recent_drinks(restaurant_id: int, days: int = 14) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT drink_name, MAX(date) as last_used, COUNT(*) as times
            FROM drink_history
            WHERE restaurant_id = ?
              AND date >= date('now', ?, 'localtime')
            GROUP BY drink_name
            ORDER BY last_used DESC
        """, (restaurant_id, f"-{days} days")).fetchall()


# ── Promos ──────────────────────────────────────────────────────────────────

def add_promo(restaurant_id: int, name: str, price: str,
              description: str = "", source: str = "manual",
              image_url: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO promos (restaurant_id, name, price, description, source, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (restaurant_id, name, price, description, source, image_url))
        conn.commit()
        return cur.lastrowid


def get_active_promos(restaurant_id: int) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM promos WHERE restaurant_id = ? AND active = 1
            ORDER BY created_at DESC LIMIT 5
        """, (restaurant_id,)).fetchall()


def deactivate_promo(promo_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE promos SET active = 0 WHERE id = ?", (promo_id,))
        conn.commit()


# ── Menú desde Facebook (actualización parcial) ──────────────────────────────

def update_menu_dishes(restaurant_id: int, soup: str, main_dish: str,
                       drink: str, updated_by: str = "Facebook"):
    """Update only soup/main_dish/drink; preserves price and initial_qty."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date = today()
    with get_conn() as conn:
        rows = conn.execute("""
            UPDATE daily_menu
            SET soup=?, main_dish=?, drink=?, updated_by=?, updated_at=?
            WHERE restaurant_id=? AND date=?
        """, (soup, main_dish, drink, updated_by, now, restaurant_id, date)).rowcount
        if rows == 0:
            conn.execute("""
                INSERT OR IGNORE INTO daily_menu
                    (restaurant_id, date, soup, main_dish, drink, price, initial_qty, current_qty, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """, (restaurant_id, date, soup, main_dish, drink, updated_by, now))
        conn.commit()


# ── Comprobantes de pago ─────────────────────────────────────────────────────

def add_payment(restaurant_id: int, cashier_name: str, amount: float,
                description: str, file_id: str, file_path: str = "",
                shift: str = "", verification_status: str = "pending",
                extracted_account: str = "", extracted_amount: float = 0,
                verification_note: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO payments
                (restaurant_id, cashier_name, amount, description, file_id, file_path,
                 shift, verification_status, extracted_account, extracted_amount, verification_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (restaurant_id, cashier_name, amount, description, file_id, file_path,
              shift, verification_status, extracted_account, extracted_amount, verification_note))
        conn.commit()
        return cur.lastrowid


def update_payment_verification(payment_id: int, status: str,
                                 extracted_account: str = "",
                                 extracted_amount: float = 0,
                                 note: str = ""):
    with get_conn() as conn:
        conn.execute("""
            UPDATE payments SET verification_status=?, extracted_account=?,
                extracted_amount=?, verification_note=?
            WHERE id=?
        """, (status, extracted_account, extracted_amount, note, payment_id))
        conn.commit()


def get_payments(restaurant_id: int, limit: int = 100) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT id, cashier_name, amount, description, file_id, file_path,
                   shift, verification_status, extracted_account, extracted_amount,
                   verification_note, registered_at
            FROM payments WHERE restaurant_id = ?
            ORDER BY registered_at DESC LIMIT ?
        """, (restaurant_id, limit)).fetchall()


def get_payments_by_shift(restaurant_id: int, shift: str,
                           date: str | None = None) -> list:
    d = date or today()
    with get_conn() as conn:
        return conn.execute("""
            SELECT id, cashier_name, amount, description, file_id, file_path,
                   shift, verification_status, extracted_account, extracted_amount,
                   verification_note, registered_at
            FROM payments
            WHERE restaurant_id=? AND shift=? AND date(registered_at)=?
            ORDER BY registered_at DESC
        """, (restaurant_id, shift, d)).fetchall()


def get_payments_by_date(restaurant_id: int, date: str) -> list:
    """Returns all payments for a restaurant on a specific date, ASC order."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT id, cashier_name, amount, description, file_id, file_path,
                   shift, verification_status, extracted_account, extracted_amount,
                   verification_note, registered_at
            FROM payments
            WHERE restaurant_id=? AND date(registered_at)=?
            ORDER BY registered_at ASC
        """, (restaurant_id, date)).fetchall()


def get_all_payments(limit: int = 200) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT p.id, r.name as restaurant_name, p.cashier_name, p.amount,
                   p.description, p.file_id, p.file_path, p.shift,
                   p.verification_status, p.extracted_account, p.extracted_amount,
                   p.verification_note, p.registered_at
            FROM payments p JOIN restaurants r ON r.id = p.restaurant_id
            ORDER BY p.registered_at DESC LIMIT ?
        """, (limit,)).fetchall()


# ── Estadísticas ─────────────────────────────────────────────────────────────

def get_sales_by_day(restaurant_id: int, days: int = 30) -> list:
    """Ventas diarias agrupadas (fecha, qty_almuerzos, total_Bs) — últimos N días."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT date,
                   SUM(CASE WHEN type='almuerzo' THEN quantity ELSE 0 END) as almuerzos,
                   SUM(CASE WHEN type='extra'    THEN quantity ELSE 0 END) as extras,
                   SUM(CASE WHEN type='refresco' THEN quantity ELSE 0 END) as refrescos,
                   SUM(amount) as total
            FROM sales
            WHERE restaurant_id=?
              AND date >= date('now', ?, 'localtime')
            GROUP BY date
            ORDER BY date ASC
        """, (restaurant_id, f"-{days-1} days")).fetchall()


def get_monthly_revenue(restaurant_id: int, months: int = 6) -> list:
    """Ingresos mensuales — últimos N meses."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT strftime('%Y-%m', date) as month,
                   SUM(amount) as total,
                   SUM(CASE WHEN type='almuerzo' THEN quantity ELSE 0 END) as almuerzos
            FROM sales
            WHERE restaurant_id=?
              AND date >= date('now', ?, 'localtime')
            GROUP BY month
            ORDER BY month ASC
        """, (restaurant_id, f"-{months} months")).fetchall()


def get_shortage_frequency(restaurant_id: int, days: int = 90) -> list:
    """Ingredientes más registrados como faltantes — ranking por frecuencia."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT item_name,
                   COUNT(*)                                     as veces,
                   SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pendientes,
                   SUM(CASE WHEN status='bought'  THEN 1 ELSE 0 END) as comprados,
                   MAX(date)                                    as ultima_vez
            FROM shortage_list
            WHERE restaurant_id=?
              AND date >= date('now', ?, 'localtime')
            GROUP BY item_name
            ORDER BY veces DESC
            LIMIT 15
        """, (restaurant_id, f"-{days} days")).fetchall()


def get_capacity_utilization(restaurant_id: int, days: int = 30) -> list:
    """Utilización diaria de capacidad: almuerzos vendidos vs inicial."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT m.date,
                   m.initial_qty,
                   COALESCE(SUM(CASE WHEN s.type='almuerzo' THEN s.quantity ELSE 0 END), 0) as vendidos,
                   ROUND(100.0 * COALESCE(SUM(CASE WHEN s.type='almuerzo' THEN s.quantity ELSE 0 END), 0)
                         / NULLIF(m.initial_qty, 0), 1) as pct
            FROM daily_menu m
            LEFT JOIN sales s ON s.restaurant_id=m.restaurant_id AND s.date=m.date
            WHERE m.restaurant_id=?
              AND m.date >= date('now', ?, 'localtime')
            GROUP BY m.date
            ORDER BY m.date ASC
        """, (restaurant_id, f"-{days-1} days")).fetchall()


def get_payments_breakdown(restaurant_id: int, days: int = 30) -> dict:
    """Desglose de comprobantes por estado de verificación."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT verification_status, COUNT(*) as cnt, SUM(amount) as total
            FROM payments
            WHERE restaurant_id=?
              AND date(registered_at) >= date('now', ?, 'localtime')
            GROUP BY verification_status
        """, (restaurant_id, f"-{days-1} days")).fetchall()
    result = {"verified": 0, "wrong_account": 0, "unreadable": 0, "pending": 0,
              "total_cnt": 0, "total_amount": 0.0}
    for r in rows:
        s = r["verification_status"]
        if s in result:
            result[s] = r["cnt"]
        result["total_cnt"] += r["cnt"]
        result["total_amount"] += (r["total"] or 0)
    return result


def get_shift_comparison(restaurant_id: int, days: int = 30) -> dict:
    """Rendimiento turno mañana vs noche (pagos + montos)."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT shift, COUNT(*) as cnt, SUM(amount) as total
            FROM payments
            WHERE restaurant_id=?
              AND date(registered_at) >= date('now', ?, 'localtime')
            GROUP BY shift
        """, (restaurant_id, f"-{days-1} days")).fetchall()
    result = {"manana": {"cnt": 0, "total": 0.0}, "noche": {"cnt": 0, "total": 0.0}}
    for r in rows:
        sh = r["shift"]
        if sh in result:
            result[sh] = {"cnt": r["cnt"], "total": round(r["total"] or 0, 2)}
    return result


def get_kpis(restaurant_id: int) -> dict:
    """KPIs clave del restaurante: este mes, semana, hoy."""
    with get_conn() as conn:
        today_s = today()
        # Hoy
        hoy = conn.execute("""
            SELECT SUM(amount) as total,
                   SUM(CASE WHEN type='almuerzo' THEN quantity ELSE 0 END) as almuerzos
            FROM sales WHERE restaurant_id=? AND date=?
        """, (restaurant_id, today_s)).fetchone()
        # Esta semana
        semana = conn.execute("""
            SELECT SUM(amount) as total
            FROM sales WHERE restaurant_id=?
              AND date >= date('now','-6 days','localtime')
        """, (restaurant_id,)).fetchone()
        # Este mes
        mes = conn.execute("""
            SELECT SUM(amount) as total,
                   SUM(CASE WHEN type='almuerzo' THEN quantity ELSE 0 END) as almuerzos
            FROM sales WHERE restaurant_id=?
              AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'localtime')
        """, (restaurant_id,)).fetchone()
        # Promedio diario (últimos 30 días con ventas)
        avg = conn.execute("""
            SELECT AVG(daily) as avg_daily FROM (
                SELECT SUM(amount) as daily FROM sales
                WHERE restaurant_id=? AND date >= date('now','-29 days','localtime')
                GROUP BY date
            )
        """, (restaurant_id,)).fetchone()
        # Mejor día del mes
        best = conn.execute("""
            SELECT date, SUM(amount) as total FROM sales
            WHERE restaurant_id=?
              AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'localtime')
            GROUP BY date ORDER BY total DESC LIMIT 1
        """, (restaurant_id,)).fetchone()
    return {
        "hoy_total":       round(hoy["total"] or 0, 2),
        "hoy_almuerzos":   hoy["almuerzos"] or 0,
        "semana_total":    round(semana["total"] or 0, 2),
        "mes_total":       round(mes["total"] or 0, 2),
        "mes_almuerzos":   mes["almuerzos"] or 0,
        "avg_diario":      round(avg["avg_daily"] or 0, 2),
        "mejor_dia_fecha": best["date"] if best and best["date"] else "—",
        "mejor_dia_total": round(best["total"] or 0, 2) if best else 0,
    }


def get_combined_stats(days: int = 30) -> dict:
    """Estadísticas combinadas ambos restaurantes para el panel del dueño."""
    oasis = get_restaurant("oasis")
    dali  = get_restaurant("dali")
    return {
        "oasis": {
            "kpis":          get_kpis(oasis["id"]),
            "sales_by_day":  [dict(r) for r in get_sales_by_day(oasis["id"], days)],
            "monthly":       [dict(r) for r in get_monthly_revenue(oasis["id"], 6)],
            "shortages":     [dict(r) for r in get_shortage_frequency(oasis["id"], 90)],
            "capacity":      [dict(r) for r in get_capacity_utilization(oasis["id"], days)],
            "payments":      get_payments_breakdown(oasis["id"], days),
            "shifts":        get_shift_comparison(oasis["id"], days),
        },
        "dali": {
            "kpis":          get_kpis(dali["id"]),
            "sales_by_day":  [dict(r) for r in get_sales_by_day(dali["id"], days)],
            "monthly":       [dict(r) for r in get_monthly_revenue(dali["id"], 6)],
            "shortages":     [dict(r) for r in get_shortage_frequency(dali["id"], 90)],
            "capacity":      [dict(r) for r in get_capacity_utilization(dali["id"], days)],
            "payments":      get_payments_breakdown(dali["id"], days),
            "shifts":        get_shift_comparison(dali["id"], days),
        },
    }


# ── Comandas (pedidos de meseros) ────────────────────────────────────────────

def create_order(restaurant_id: int, mesero_id: str, mesero_name: str,
                 table_ref: str, items: str, notes: str = "") -> int:
    """Crea un nuevo pedido, retorna su ID."""
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO orders (restaurant_id, mesero_id, mesero_name,
                                table_ref, items, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (restaurant_id, str(mesero_id), mesero_name, table_ref, items, notes))
        conn.commit()
        return cur.lastrowid


def get_orders_today(restaurant_id: int, status: str | None = None) -> list:
    """Todos los pedidos de HOY para un restaurante, ordenados por creación ASC."""
    date = today()
    with get_conn() as conn:
        if status:
            return conn.execute("""
                SELECT * FROM orders
                WHERE restaurant_id = ? AND date(created_at) = ? AND status = ?
                ORDER BY created_at ASC
            """, (restaurant_id, date, status)).fetchall()
        return conn.execute("""
            SELECT * FROM orders
            WHERE restaurant_id = ? AND date(created_at) = ?
            ORDER BY created_at ASC
        """, (restaurant_id, date)).fetchall()


def get_orders_by_mesero_today(restaurant_id: int, mesero_id: str) -> list:
    """Pedidos del mesero de HOY en ese restaurante."""
    date = today()
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM orders
            WHERE restaurant_id = ? AND mesero_id = ? AND date(created_at) = ?
            ORDER BY created_at ASC
        """, (restaurant_id, str(mesero_id), date)).fetchall()


def get_order_by_id(order_id: int) -> "sqlite3.Row | None":
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()


def mark_order_ready(order_id: int) -> bool:
    """Marca el pedido como listo para servir. Retorna True si existía."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE orders SET status = 'ready', ready_at = ?
            WHERE id = ? AND status = 'pending'
        """, (now, order_id))
        conn.commit()
        return cur.rowcount > 0


def mark_order_served(order_id: int, mesero_id: str) -> bool:
    """Marca el pedido como entregado al cliente. Solo el mesero que lo creó."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE orders SET status = 'served', served_at = ?
            WHERE id = ? AND mesero_id = ? AND status IN ('pending', 'ready')
        """, (now, order_id, str(mesero_id)))
        conn.commit()
        return cur.rowcount > 0


# ── Mesas (asignación de meseros) ────────────────────────────────────────────

def assign_tables(restaurant_id: int, mesero_id: str, mesero_name: str,
                  tables: list) -> list:
    """Asigna mesas al mesero para hoy (INSERT OR REPLACE).
    Retorna lista de (table_number, mesero_anterior) para las reasignadas."""
    date_val = today()
    taken = []
    with get_conn() as conn:
        for table in tables:
            existing = conn.execute("""
                SELECT mesero_id, mesero_name FROM table_assignments
                WHERE restaurant_id = ? AND table_number = ? AND date = ?
            """, (restaurant_id, table, date_val)).fetchone()
            if existing and existing["mesero_id"] != str(mesero_id):
                taken.append((table, existing["mesero_name"]))
            conn.execute("""
                INSERT OR REPLACE INTO table_assignments
                    (restaurant_id, mesero_id, mesero_name, table_number, date)
                VALUES (?, ?, ?, ?, ?)
            """, (restaurant_id, str(mesero_id), mesero_name, table, date_val))
        conn.commit()
    return taken


def get_mesero_tables(restaurant_id: int, mesero_id: str) -> list:
    """Retorna lista de strings con los números de mesa del mesero hoy."""
    date_val = today()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT table_number FROM table_assignments
            WHERE restaurant_id = ? AND mesero_id = ? AND date = ?
            ORDER BY table_number
        """, (restaurant_id, str(mesero_id), date_val)).fetchall()
    return [r["table_number"] for r in rows]


def get_all_table_assignments(restaurant_id: int) -> list:
    """Todas las asignaciones de hoy, ordenadas por nombre del mesero y mesa."""
    date_val = today()
    with get_conn() as conn:
        return conn.execute("""
            SELECT table_number, mesero_id, mesero_name
            FROM table_assignments
            WHERE restaurant_id = ? AND date = ?
            ORDER BY mesero_name, table_number
        """, (restaurant_id, date_val)).fetchall()


def clear_mesero_tables(restaurant_id: int, mesero_id: str) -> int:
    """Elimina TODAS las asignaciones del mesero hoy. Retorna cuántas eliminó."""
    date_val = today()
    with get_conn() as conn:
        cur = conn.execute("""
            DELETE FROM table_assignments
            WHERE restaurant_id = ? AND mesero_id = ? AND date = ?
        """, (restaurant_id, str(mesero_id), date_val))
        conn.commit()
        return cur.rowcount
