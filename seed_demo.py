"""Carga datos de demo para ver el panel web funcionando."""
import os, sqlite3
os.environ["DB_PATH"] = "demo_restaurante.db"

import database as db

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

print("OK - Datos de demo cargados correctamente.")
