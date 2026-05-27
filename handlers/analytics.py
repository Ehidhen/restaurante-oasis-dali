"""
Análisis predictivo con IA — genera insights y predicciones a partir
de los datos históricos acumulados de ambos restaurantes.
Usa Claude Haiku para minimizar costo; el resultado se cachea en memoria
durante 30 minutos para no llamar la API en cada recarga.
"""
import os
import time
import json
import logging

logger = logging.getLogger(__name__)

_cache: dict = {"ts": 0, "data": None}
_CACHE_TTL = 1800  # 30 min


def _call_claude(prompt: str) -> str:
    """Llama a Claude Haiku y retorna el texto de respuesta."""
    try:
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return ""
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Analytics IA error: {e}")
        return ""


def _build_prompt(stats: dict) -> str:
    o = stats["oasis"]
    d = stats["dali"]

    def fmt_shortages(sh_list):
        return ", ".join(f"{s['item_name']} ({s['veces']}x)" for s in sh_list[:8]) or "ninguno"

    def fmt_kpis(k):
        return (f"Hoy Bs {k['hoy_total']} ({k['hoy_almuerzos']} almuerzos) | "
                f"Semana Bs {k['semana_total']} | Mes Bs {k['mes_total']} | "
                f"Promedio diario Bs {k['avg_diario']}")

    # Tendencia últimos 7 días
    def trend(sales_days):
        last7 = sales_days[-7:] if len(sales_days) >= 7 else sales_days
        if len(last7) < 2:
            return "sin datos"
        totals = [r["total"] for r in last7]
        diff = totals[-1] - totals[0]
        pct = round(diff / totals[0] * 100, 1) if totals[0] else 0
        return f"{'▲' if diff >= 0 else '▼'} {abs(pct)}% vs hace 7 días"

    prompt = f"""Eres el asistente de análisis del sistema de gestión de dos restaurantes bolivianos: Oasis y Dali.
Analiza los siguientes datos y responde en español con formato JSON.

=== DATOS ===

OASIS:
- KPIs: {fmt_kpis(o['kpis'])}
- Tendencia ventas: {trend(o['sales_by_day'])}
- Ingredientes más registrados como faltantes: {fmt_shortages(o['shortages'])}
- Utilización promedio de capacidad: {round(sum(r.get('pct') or 0 for r in o['capacity']) / max(len(o['capacity']),1), 1)}%
- Pagos verificados: {o['payments']['verified']} ok / {o['payments']['wrong_account']} cta.incorrecta / {o['payments']['pending']} pendientes

DALI:
- KPIs: {fmt_kpis(d['kpis'])}
- Tendencia ventas: {trend(d['sales_by_day'])}
- Ingredientes más registrados como faltantes: {fmt_shortages(d['shortages'])}
- Utilización promedio de capacidad: {round(sum(r.get('pct') or 0 for r in d['capacity']) / max(len(d['capacity']),1), 1)}%
- Pagos verificados: {d['payments']['verified']} ok / {d['payments']['wrong_account']} cta.incorrecta / {d['payments']['pending']} pendientes

=== INSTRUCCIONES ===
Genera un JSON con exactamente estas claves (sin texto antes ni después del JSON):
{{
  "resumen": "2-3 oraciones sobre el estado general del negocio",
  "oasis_insight": "1-2 oraciones: qué está yendo bien o mal en Oasis",
  "dali_insight": "1-2 oraciones: qué está yendo bien o mal en Dali",
  "prediccion_ingredientes": ["ingrediente1", "ingrediente2", "ingrediente3"],
  "prediccion_ingredientes_razon": "por qué predices que esos ingredientes serán necesarios",
  "alerta": "alerta más importante de hoy (o vacío si todo está bien)",
  "recomendacion": "1 acción concreta que el dueño debería tomar esta semana",
  "tendencia_30d": "sube/baja/estable"
}}"""
    return prompt


def get_ai_analysis(stats: dict) -> dict:
    """
    Retorna análisis IA. Usa caché de 30 min para evitar llamadas repetidas.
    Si la API no está configurada o falla, retorna un análisis básico de reglas.
    """
    global _cache
    now = time.time()

    if _cache["data"] and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    # Intentar con IA
    raw = _call_claude(_build_prompt(stats))
    result = None

    if raw:
        try:
            # Extraer JSON aunque venga con texto extra
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw[start:end])
        except Exception:
            result = None

    # Fallback: análisis basado en reglas
    if not result:
        result = _rule_based_analysis(stats)

    result["source"] = "ia" if raw and result.get("resumen") else "reglas"
    _cache = {"ts": now, "data": result}
    return result


def _rule_based_analysis(stats: dict) -> dict:
    """Análisis básico sin IA usando reglas sobre los datos."""
    o_kpi = stats["oasis"]["kpis"]
    d_kpi = stats["dali"]["kpis"]
    o_sh  = stats["oasis"]["shortages"]
    d_sh  = stats["dali"]["shortages"]
    o_pay = stats["oasis"]["payments"]
    d_pay = stats["dali"]["payments"]

    # Ingrediente más frecuente global
    all_sh = sorted(o_sh + d_sh, key=lambda x: x["veces"], reverse=True)
    top3   = [s["item_name"] for s in all_sh[:3]]

    # Alerta de pagos incorrectos
    alertas = []
    if o_pay["wrong_account"] > 0:
        alertas.append(f"Oasis tiene {o_pay['wrong_account']} pago(s) con cuenta incorrecta")
    if d_pay["wrong_account"] > 0:
        alertas.append(f"Dali tiene {d_pay['wrong_account']} pago(s) con cuenta incorrecta")
    if o_pay["pending"] + d_pay["pending"] > 3:
        alertas.append(f"{o_pay['pending'] + d_pay['pending']} comprobantes pendientes de revisión")

    total_mes = o_kpi["mes_total"] + d_kpi["mes_total"]
    avg = (o_kpi["avg_diario"] + d_kpi["avg_diario"]) / 2

    return {
        "resumen": (f"Ambos restaurantes llevan Bs {total_mes:.0f} este mes. "
                    f"Promedio diario combinado: Bs {avg:.0f}. "
                    f"Sistema operando normalmente."),
        "oasis_insight": (f"Oasis: Bs {o_kpi['mes_total']:.0f} este mes, "
                          f"{o_kpi['mes_almuerzos']} almuerzos. "
                          f"Promedio diario Bs {o_kpi['avg_diario']:.0f}."),
        "dali_insight": (f"Dali: Bs {d_kpi['mes_total']:.0f} este mes, "
                         f"{d_kpi['mes_almuerzos']} almuerzos. "
                         f"Promedio diario Bs {d_kpi['avg_diario']:.0f}."),
        "prediccion_ingredientes": top3,
        "prediccion_ingredientes_razon": (
            "Basado en frecuencia histórica de faltantes registrados en el sistema."),
        "alerta": alertas[0] if alertas else "",
        "recomendacion": (
            f"Reabastecer {top3[0]} antes del próximo turno — "
            "es el ingrediente más frecuentemente agotado." if top3 else
            "Mantener el ritmo actual de operaciones."),
        "tendencia_30d": "estable",
    }
