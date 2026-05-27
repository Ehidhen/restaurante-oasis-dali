"""Carga datos de demo para ver el panel web funcionando."""
import os, sqlite3
os.environ["DB_PATH"] = "demo_restaurante.db"

import database as db

# Limpiar datos anteriores para evitar duplicados al re-ejecutar
_clean = sqlite3.connect("demo_restaurante.db")
for t in ("shortage_list","sales","daily_menu","extra_dishes",
          "transfers","promos","drink_history","payments","social_posts"):
    _clean.execute(f"DELETE FROM {t}")
_clean.commit()
_clean.close()

db.init_db()

oasis = db.get_restaurant("oasis")
dali  = db.get_restaurant("dali")

# ── Menú del día ──────────────────────────────────────────────────────────
db.set_menu(oasis["id"], "Sopa de pollo con fideos",
            "Arroz con carne guisada + ensalada", "Jugo de mora",
            8.50, 60, updated_by="Maria Garcia")
db.set_menu(dali["id"], "Crema de espinaca",
            "Seco de pollo + menestra + arroz", "Limonada",
            9.00, 45, updated_by="Pedro Ramirez")

# Ajustar contadores actuales
db.set_qty(oasis["id"], 18)
db.set_qty(dali["id"],  4)

# ── Ventas registradas hoy ────────────────────────────────────────────────
for _ in range(42):
    db.register_sale(oasis["id"], "almuerzo", 1, 8.50, "cajera_oasis")
for _ in range(41):
    db.register_sale(dali["id"],  "almuerzo", 1, 9.00, "cajero_dali")

db.register_sale(oasis["id"], "refresco", 5,  10.00, "cajera_oasis")
db.register_sale(dali["id"],  "refresco", 3,   6.00, "cajero_dali")
db.register_sale(oasis["id"], "extra",    2,  10.00, "cajera_oasis")
db.register_sale(dali["id"],  "extra",    1,   5.00, "cajero_dali")

# ── Faltantes Oasis (con nombres y horas distintas) ───────────────────────
db.add_shortage(oasis["id"], "Tomates",       "5 kg",       "Maria Garcia")
db.add_shortage(oasis["id"], "Cebollas",      "3 kg",       "Maria Garcia")
db.add_shortage(oasis["id"], "Papas",         "10 kg",      "Luis Mendoza")
db.add_shortage(oasis["id"], "Aceite vegetal","2 litros",   "Luis Mendoza")
db.add_shortage(oasis["id"], "Servilletas",   "2 paquetes", "Maria Garcia")
db.mark_shortage_bought(oasis["id"], "Aceite vegetal", "Luis Mendoza")

# ── Faltantes Dali ────────────────────────────────────────────────────────
db.add_shortage(dali["id"], "Pollo",          "8 kg",    "Pedro Ramirez")
db.add_shortage(dali["id"], "Arroz",          "5 kg",    "Ana Torres")
db.add_shortage(dali["id"], "Lentejas",       "2 kg",    "Ana Torres")
db.add_shortage(dali["id"], "Detergente loza","1 unidad", "Pedro Ramirez")
db.add_shortage(dali["id"], "Bolsas basura",  "1 rollo",  "Ana Torres")
db.mark_shortage_bought(dali["id"], "Bolsas basura", "Ana Torres")

# ── Platos extra ──────────────────────────────────────────────────────────
db.add_extra_dish(oasis["id"], "Pollo a la plancha", 5.00)
db.add_extra_dish(oasis["id"], "Ensalada grande",    2.50)
db.add_extra_dish(dali["id"],  "Churrasco",          7.00)
db.add_extra_dish(dali["id"],  "Sopa sola",          2.00)

# ── Transferencia del dia ─────────────────────────────────────────────────
tid = db.create_transfer(dali["id"], oasis["id"], 10, "Pedro Ramirez")
db.update_transfer_status(tid, "sent")

# ── Promos activas ────────────────────────────────────────────────────────
db.add_promo(oasis["id"], "Frappe de frutas", "2x35 Bs", "Promo especial de lunes", source="facebook")
db.add_promo(oasis["id"], "Alitas picantes",  "2x65 Bs", "Los martes con cualquier almuerzo", source="facebook")
db.add_promo(dali["id"],  "Combo familiar",   "45 Bs",   "Seco + postre + refresco", source="manual")

# ── Historial de bebidas (rotación últimos días) ───────────────────────────
# Simula bebidas servidas recientemente para que la sugerencia evite repetir
conn2 = sqlite3.connect("demo_restaurante.db")
conn2.execute("INSERT INTO drink_history(restaurant_id,drink_name,date) VALUES(?,?,date('now','-1 day'))",
              (oasis["id"], "Jugo de maracuyá"))
conn2.execute("INSERT INTO drink_history(restaurant_id,drink_name,date) VALUES(?,?,date('now','-3 day'))",
              (oasis["id"], "Frappe de maracuyá"))
conn2.execute("INSERT INTO drink_history(restaurant_id,drink_name,date) VALUES(?,?,date('now','-2 day'))",
              (dali["id"], "Limonada de maracuyá"))
conn2.execute("INSERT INTO drink_history(restaurant_id,drink_name,date) VALUES(?,?,date('now','-5 day'))",
              (dali["id"], "Jugo de naranja"))
conn2.commit()
conn2.close()

# Ajustar timestamps para que se vean distintos en el demo
conn = sqlite3.connect("demo_restaurante.db")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 07:30:00' WHERE item_name='Tomates'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 07:30:00' WHERE item_name='Cebollas'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 08:15:00' WHERE item_name='Papas'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 08:15:00' WHERE item_name='Aceite vegetal'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 09:00:00' WHERE item_name='Servilletas'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 07:45:00' WHERE item_name='Pollo'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 08:30:00' WHERE item_name='Arroz'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 08:30:00' WHERE item_name='Lentejas'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 07:45:00' WHERE item_name='Detergente loza'")
conn.execute("UPDATE shortage_list SET updated_at = '2026-05-25 09:10:00' WHERE item_name='Bolsas basura'")
conn.execute("UPDATE daily_menu SET updated_at='2026-05-25 06:50:00' WHERE restaurant_id=1")
conn.execute("UPDATE daily_menu SET updated_at='2026-05-25 07:05:00' WHERE restaurant_id=2")
conn.commit()
conn.close()

# ── Comprobantes de pago demo (con turno y verificación) ──────────────────
# Turno mañana — Oasis
db.add_payment(oasis["id"], "Maria Garcia",  35.00, "QR Mesa 3",
               file_id="demo1", file_path="", shift="manana",
               verification_status="verified",  extracted_account="77712345", extracted_amount=35.0)
db.add_payment(oasis["id"], "Maria Garcia",  70.00, "QR Mesa 7 - 2 platos",
               file_id="demo2", file_path="", shift="manana",
               verification_status="verified",  extracted_account="77712345", extracted_amount=70.0)
db.add_payment(oasis["id"], "Luis Mendoza",  35.00, "QR efectivo",
               file_id="demo3", file_path="", shift="manana",
               verification_status="wrong_account", extracted_account="77799999", extracted_amount=35.0)
# Turno noche — Oasis
db.add_payment(oasis["id"], "Maria Garcia",  45.00, "QR Mesa 2",
               file_id="demo6", file_path="", shift="noche",
               verification_status="verified",  extracted_account="77712345", extracted_amount=45.0)
db.add_payment(oasis["id"], "Maria Garcia",  35.00, "QR Mesa 9",
               file_id="demo7", file_path="", shift="noche",
               verification_status="unreadable", extracted_account="", extracted_amount=0)
# Turno mañana — Dali
db.add_payment(dali["id"],  "Ana Torres",    45.00, "QR Mesa 1",
               file_id="demo4", file_path="", shift="manana",
               verification_status="verified",  extracted_account="77798765", extracted_amount=45.0)
db.add_payment(dali["id"],  "Pedro Ramirez", 90.00, "QR Mesa 5 - combo",
               file_id="demo5", file_path="", shift="manana",
               verification_status="verified",  extracted_account="77798765", extracted_amount=90.0)
# Turno noche — Dali
db.add_payment(dali["id"],  "Ana Torres",    35.00, "QR Mesa 3",
               file_id="demo8", file_path="", shift="noche",
               verification_status="pending",   extracted_account="", extracted_amount=0)

# ── Datos históricos para estadísticas (últimos 35 días) ─────────────────────
import random, sqlite3 as _sql

_hist = _sql.connect("demo_restaurante.db")

# Patrones realistas: lunes-viernes más ventas, fin de semana menos
_oasis_price = 8.50
_dali_price  = 9.00

# Ingredientes que se van agotando con frecuencia por restaurante
_oasis_recurrent = ["Tomates", "Cebollas", "Papas", "Aceite vegetal", "Servilletas",
                    "Pollo", "Sal", "Arroz", "Cebolla", "Tomates", "Papas"]
_dali_recurrent  = ["Pollo", "Arroz", "Lentejas", "Tomates", "Detergente loza",
                    "Bolsas basura", "Arroz", "Pollo", "Lentejas", "Cebollas"]

random.seed(42)  # reproducible

for offset in range(35, 0, -1):
    d = f"date('now','-{offset} days','localtime')"
    ds = f"-{offset} days"  # para fecha literal en SQLite

    # Almuerzos vendidos Oasis (35-55 entre semana, 20-30 fines)
    dow = (offset % 7)
    is_weekend = dow in (0, 6)
    o_alm = random.randint(20, 30) if is_weekend else random.randint(35, 55)
    d_alm = random.randint(15, 25) if is_weekend else random.randint(28, 45)
    o_init = o_alm + random.randint(5, 18)
    d_init = d_alm + random.randint(3, 15)

    # Insertar menú histórico
    for rid, alm, init, price in [
        (oasis["id"], o_alm, o_init, _oasis_price),
        (dali["id"],  d_alm, d_init, _dali_price)
    ]:
        soups  = ["Sopa de pollo", "Crema de zapallo", "Sopa de res", "Caldo de pollo",
                  "Sopa de verduras", "Crema de espinaca", "Locro de papa"]
        mains  = ["Arroz con pollo", "Seco de res", "Churrasco + ensalada",
                  "Pollo a la plancha + menestra", "Arroz con carne guisada",
                  "Seco de pollo + arroz", "Milanesa + papas"]
        drinks = ["Jugo de naranja", "Limonada", "Jugo de maracuyá",
                  "Refresco de durazno", "Jugo de mora", "Limonada de maracuyá"]
        _hist.execute("""
            INSERT OR IGNORE INTO daily_menu
              (restaurant_id, date, soup, main_dish, drink, price, initial_qty, current_qty, updated_by)
            VALUES (?, date('now', ?, 'localtime'), ?, ?, ?, ?, ?, ?, 'Demo')
        """, (rid, ds, random.choice(soups), random.choice(mains),
              random.choice(drinks), price, init, init - alm))

    # Insertar ventas Oasis
    o_extras  = random.randint(0, 4)
    o_refres  = random.randint(2, 8)
    for _ in range(o_alm):
        _hist.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, date('now', ?, 'localtime'), 'almuerzo', 1, ?, 'cajera_oasis')
        """, (oasis["id"], ds, _oasis_price))
    if o_extras:
        _hist.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, date('now', ?, 'localtime'), 'extra', ?, ?, 'cajera_oasis')
        """, (oasis["id"], ds, o_extras, o_extras * 4.5))
    if o_refres:
        _hist.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, date('now', ?, 'localtime'), 'refresco', ?, ?, 'cajera_oasis')
        """, (oasis["id"], ds, o_refres, o_refres * 3.5))

    # Insertar ventas Dali
    d_extras  = random.randint(0, 3)
    d_refres  = random.randint(1, 6)
    for _ in range(d_alm):
        _hist.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, date('now', ?, 'localtime'), 'almuerzo', 1, ?, 'cajero_dali')
        """, (dali["id"], ds, _dali_price))
    if d_extras:
        _hist.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, date('now', ?, 'localtime'), 'extra', ?, ?, 'cajero_dali')
        """, (dali["id"], ds, d_extras, d_extras * 5.0))
    if d_refres:
        _hist.execute("""
            INSERT INTO sales (restaurant_id, date, type, quantity, amount, cashier_id)
            VALUES (?, date('now', ?, 'localtime'), 'refresco', ?, ?, 'cajero_dali')
        """, (dali["id"], ds, d_refres, d_refres * 3.5))

    # Faltantes históricos (cada 3-4 días algo falta)
    if offset % 3 == 0:
        item_o = random.choice(_oasis_recurrent)
        item_d = random.choice(_dali_recurrent)
        for rid, item in [(oasis["id"], item_o), (dali["id"], item_d)]:
            qty_label = random.choice(["2 kg", "5 kg", "1 caja", "3 unidades", "500 g"])
            status    = random.choice(["bought", "bought", "bought", "pending"])
            _hist.execute("""
                INSERT INTO shortage_list (restaurant_id, item_name, quantity_needed, date, status, updated_by, updated_at)
                VALUES (?, ?, ?, date('now', ?, 'localtime'), ?, 'Demo', datetime('now', ?, 'localtime'))
            """, (rid, item, qty_label, ds, status, ds))

    # Pagos históricos (2-5 por día)
    n_pay = random.randint(2, 5)
    for i in range(n_pay):
        rid   = random.choice([oasis["id"], dali["id"]])
        amt   = round(random.choice([35, 35, 35, 70, 45, 90, 52.5]) , 2)
        st    = random.choices(["verified","verified","verified","wrong_account","pending"],
                               weights=[75, 5, 5, 10, 5])[0]
        shift = "manana" if i < n_pay // 2 + 1 else "noche"
        _hist.execute("""
            INSERT INTO payments (restaurant_id, cashier_name, amount, description,
                                  file_id, file_path, shift, verification_status,
                                  extracted_account, extracted_amount, registered_at)
            VALUES (?, 'Demo Mesero', ?, 'QR histórico', '', '', ?, ?, '', 0,
                    datetime('now', ?, 'localtime'))
        """, (rid, amt, shift, st, ds))

_hist.commit()
_hist.close()

print("OK - Datos de demo cargados correctamente.")

