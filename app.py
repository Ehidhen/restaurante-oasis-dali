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


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
