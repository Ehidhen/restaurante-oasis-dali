from flask import Flask, render_template, jsonify
import database as db
import config
from datetime import datetime

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
        "oasis": _build_restaurant_data("oasis"),
        "dali":  _build_restaurant_data("dali"),
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
