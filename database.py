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
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id  TEXT UNIQUE NOT NULL,
            name         TEXT NOT NULL,
            role         TEXT NOT NULL,
            restaurant_id INTEGER REFERENCES restaurants(id)
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
    """)

    # Seed restaurantes
    c.execute("INSERT OR IGNORE INTO restaurants (name) VALUES ('oasis')")
    c.execute("INSERT OR IGNORE INTO restaurants (name) VALUES ('dali')")

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


def upsert_user(telegram_id: str, name: str, role: str, restaurant_id: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, name, role, restaurant_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name=excluded.name, role=excluded.role,
                restaurant_id=excluded.restaurant_id
        """, (str(telegram_id), name, role, restaurant_id))
        conn.commit()


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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE shortage_list SET status = 'bought', updated_by = ?, updated_at = ?
            WHERE restaurant_id = ? AND item_name LIKE ? AND status = 'pending'
        """, (updated_by, now, restaurant_id, f"%{item_name}%"))
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
