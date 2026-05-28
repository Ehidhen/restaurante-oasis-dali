import os
from flask import Flask, render_template, jsonify, send_from_directory, abort, request
import database as db
import config
from datetime import datetime
from handlers.refrescos import sugerir_refresco
from handlers.social import get_latest_posts_summary
from handlers.analytics import get_ai_analysis

COMPROBANTES_DIR = os.getenv("COMPROBANTES_DIR", "comprobantes")

app = Flask(__name__)


def _build_restaurant_data(name: str) -> dict:
    rest = db.get_restaurant(name)
    if not rest:
        return {}
    rid = rest["id"]
    menu = db.get_menu(rid)
    qty = db.get_current_qty(rid)
    summary = db.get_daily_summary(rid)
    shortages = db.get_all_shortages_today(rid)
    transfers = db.get_today_transfers(rid)

    alm_qty, alm_tot = summary.get("almuerzo", (0, 0.0))
    ext_qty, ext_tot = summary.get("extra", (0, 0.0))
    ref_qty, ref_tot = summary.get("refresco", (0, 0.0))
    total_income = summary.get("total", 0.0)

    if qty == 0:
        estado = "SIN_ALMUERZOS"
    elif qty <= config.ALERT_LOW_THRESHOLD:
        estado = "POCAS_UNIDADES"
    else:
        estado = "ABIERTO"

    promos = db.get_active_promos(rid)
    drink_sug = sugerir_refresco(rid)

    return {
        "name": name,
        "label": "🌴 Oasis" if name == "oasis" else "🎨 Dali",
        "estado": estado,
        "qty": qty,
        "menu": {
            "soup":       menu["soup"]       if menu else None,
            "main_dish":  menu["main_dish"]  if menu else None,
            "drink":      menu["drink"]      if menu else None,
            "price":      menu["price"]      if menu else 0.0,
            "initial":    menu["initial_qty"] if menu else 0,
            "updated_by": menu["updated_by"] if menu else "—",
            "updated_at": menu["updated_at"] if menu else "—",
        } if menu else None,
        "sales": {
            "almuerzos": alm_qty,
            "almuerzos_total": alm_tot,
            "extras": ext_qty,
            "extras_total": ext_tot,
            "refrescos": ref_qty,
            "refrescos_total": ref_tot,
            "total": total_income,
        },
        "shortages": [
            {
                "item_name":       s["item_name"],
                "quantity_needed": s["quantity_needed"],
                "status":          s["status"],
                "updated_by":      s["updated_by"] if "updated_by" in s.keys() else "Sistema",
                "updated_at":      s["updated_at"] if "updated_at" in s.keys() else "—",
            }
            for s in shortages
        ],
        "transfers": [
            {
                "from": t["from_name"],
                "to": t["to_name"],
                "quantity": t["quantity"],
                "status": t["status"],
                "created_at": t["created_at"],
            }
            for t in transfers
        ],
        "promos": [
            {
                "name": p["name"],
                "price": p["price"],
                "description": p["description"],
                "source": p["source"],
                "created_at": p["created_at"],
            }
            for p in promos
        ],
        "drink_suggestion": drink_sug,
    }


@app.route("/")
def index():
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    oasis = _build_restaurant_data("oasis")
    dali  = _build_restaurant_data("dali")
    return render_template("index.html", oasis=oasis, dali=dali, now=now)


@app.route("/api/status")
def api_status():
    """JSON endpoint for auto-refresh polling."""
    return jsonify({
        "oasis":        _build_restaurant_data("oasis"),
        "dali":         _build_restaurant_data("dali"),
        "social_posts": get_latest_posts_summary(),
        "timestamp":    datetime.now().isoformat(),
    })


@app.route("/api/payments")
def api_payments():
    oasis = db.get_restaurant("oasis")
    dali  = db.get_restaurant("dali")
    return jsonify({
        "oasis": [dict(p) for p in db.get_payments(oasis["id"])],
        "dali":  [dict(p) for p in db.get_payments(dali["id"])],
    })


@app.route("/comprobantes/<path:filename>")
def serve_comprobante(filename):
    safe = os.path.basename(filename)
    if not safe.endswith(".jpg"):
        abort(404)
    return send_from_directory(os.path.abspath(COMPROBANTES_DIR), safe)


@app.route("/api/stats")
def api_stats():
    """Panel de estadísticas para el dueño."""
    days = int(request.args.get("days", 30))
    days = max(7, min(days, 365))
    stats = db.get_combined_stats(days)
    return jsonify(stats)


@app.route("/api/stats/ai")
def api_stats_ai():
    """Análisis IA predictivo (caché 30 min)."""
    stats = db.get_combined_stats(30)
    analysis = get_ai_analysis(stats)
    return jsonify(analysis)


@app.route("/health")
def health():
    return "OK", 200


# ── Mobile App API (/api/app/*) ──────────────────────────────────────────────

def _get_rid(restaurant: str):
    """Helper: get restaurant row or None."""
    return db.get_restaurant(restaurant.lower())


@app.route("/api/app/orders/<restaurant>")
def app_orders(restaurant):
    rest = _get_rid(restaurant)
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    orders = db.get_orders_today(rest["id"])
    return jsonify([
        {
            "id":          o["id"],
            "mesero_name": o["mesero_name"],
            "mesero_id":   o["mesero_id"],
            "table_ref":   o["table_ref"],
            "items":       o["items"],
            "notes":       o["notes"],
            "status":      o["status"],
            "created_at":  o["created_at"],
            "ready_at":    o["ready_at"],
            "served_at":   o["served_at"],
        }
        for o in orders
    ])


@app.route("/api/app/cuadre/<restaurant>")
def app_cuadre(restaurant):
    rest = _get_rid(restaurant)
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    rid   = rest["id"]
    today = db.today()

    summary  = db.get_daily_summary(rid)
    payments = db.get_payments_by_date(rid, today)
    orders   = db.get_orders_today(rid)

    alm_qty, alm_tot = summary.get("almuerzo", (0, 0.0))
    ext_qty, ext_tot = summary.get("extra",    (0, 0.0))
    total_ventas     = summary.get("total",    0.0)

    total_pagos  = sum(p["amount"] or 0 for p in payments)
    pagos_wrong  = sum(1 for p in payments if p["verification_status"] == "wrong_account")
    orders_served = sum(1 for o in orders if o["status"] == "served")
    orders_ready  = sum(1 for o in orders if o["status"] == "ready")
    orders_pend   = sum(1 for o in orders if o["status"] == "pending")

    return jsonify({
        "total_ventas":   round(total_ventas, 2),
        "total_pagos":    round(total_pagos, 2),
        "diferencia":     round(total_ventas - total_pagos, 2),
        "almuerzos":      alm_qty,
        "almuerzos_total": round(alm_tot, 2),
        "extras":         ext_qty,
        "extras_total":   round(ext_tot, 2),
        "orders_served":  orders_served,
        "orders_ready":   orders_ready,
        "orders_pending": orders_pend,
        "pagos_wrong":    pagos_wrong,
        "num_pagos":      len(payments),
    })


@app.route("/api/app/menu/<restaurant>")
def app_menu(restaurant):
    rest = _get_rid(restaurant)
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    menu = db.get_menu(rest["id"])
    if not menu:
        return jsonify(None)
    return jsonify({
        "soup":        menu["soup"],
        "main_dish":   menu["main_dish"],
        "drink":       menu["drink"],
        "price":       menu["price"],
        "initial_qty": menu["initial_qty"],
        "current_qty": menu["current_qty"],
        "updated_by":  menu["updated_by"],
        "updated_at":  menu["updated_at"],
    })


@app.route("/api/app/shortages/<restaurant>")
def app_shortages(restaurant):
    rest = _get_rid(restaurant)
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    items = db.get_all_shortages_today(rest["id"])
    return jsonify([
        {
            "id":              s["id"],
            "item_name":       s["item_name"],
            "quantity_needed": s["quantity_needed"],
            "status":          s["status"],
            "updated_by":      s["updated_by"],
            "updated_at":      s["updated_at"],
        }
        for s in items
    ])


@app.route("/api/app/venta", methods=["POST"])
def app_venta():
    data = request.get_json(force=True)
    restaurant = data.get("restaurant", "")
    qty        = int(data.get("qty", 1))
    if qty < 1:
        return jsonify({"error": "qty must be >= 1"}), 400
    rest = _get_rid(restaurant)
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    rid   = rest["id"]
    menu  = db.get_menu(rid)
    price = menu["price"] if menu else 0.0
    db.register_sale(rid, "almuerzo", qty, price * qty, "app")
    new_qty = db.adjust_qty(rid, -qty)
    return jsonify({"ok": True, "new_qty": new_qty, "amount": round(price * qty, 2)})


@app.route("/api/app/pedido", methods=["POST"])
def app_pedido():
    data  = request.get_json(force=True)
    rest  = _get_rid(data.get("restaurant", ""))
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    mesero = str(data.get("mesero", "app_user"))
    table  = str(data.get("table", ""))
    items  = str(data.get("items", "")).strip()
    if not items:
        return jsonify({"error": "items required"}), 400
    oid = db.create_order(rest["id"], mesero, mesero, table, items)
    return jsonify({"ok": True, "order_id": oid})


@app.route("/api/app/order_ready", methods=["POST"])
def app_order_ready():
    data     = request.get_json(force=True)
    order_id = int(data.get("order_id", 0))
    ok       = db.mark_order_ready(order_id)
    if not ok:
        return jsonify({"error": "order not found or not pending"}), 404
    return jsonify({"ok": True})


@app.route("/api/app/order_served", methods=["POST"])
def app_order_served():
    data      = request.get_json(force=True)
    order_id  = int(data.get("order_id", 0))
    mesero_id = str(data.get("mesero_id", "app_user"))
    ok        = db.mark_order_served(order_id, mesero_id)
    if not ok:
        return jsonify({"error": "order not found or already served"}), 404
    return jsonify({"ok": True})


@app.route("/api/app/faltante", methods=["POST"])
def app_faltante():
    data = request.get_json(force=True)
    rest = _get_rid(data.get("restaurant", ""))
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    item = str(data.get("item", "")).strip()
    qty  = str(data.get("qty", "")).strip()
    user = str(data.get("user", "App"))
    if not item:
        return jsonify({"error": "item required"}), 400
    db.add_shortage(rest["id"], item, qty or "1", user)
    return jsonify({"ok": True})


@app.route("/api/app/comprado", methods=["POST"])
def app_comprado():
    data = request.get_json(force=True)
    rest = _get_rid(data.get("restaurant", ""))
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    item = str(data.get("item", "")).strip()
    ok   = db.mark_shortage_bought(rest["id"], item, "App")
    return jsonify({"ok": ok})


@app.route("/api/app/ajustar", methods=["POST"])
def app_ajustar():
    data = request.get_json(force=True)
    rest = _get_rid(data.get("restaurant", ""))
    if not rest:
        return jsonify({"error": "restaurant not found"}), 404
    qty  = int(data.get("qty", 0))
    new  = db.set_qty(rest["id"], qty)
    return jsonify({"ok": True, "new_qty": new})


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
