"""
Análisis de comprobantes de pago con Claude Vision.
Extrae número de cuenta destino y monto de la imagen.
"""
import base64
import json
import logging
import os

logger = logging.getLogger(__name__)

_PROMPT = (
    "Eres un asistente que analiza comprobantes de pago bolivianos "
    "(transferencias QR, Tigo Money, banco, billetera digital). "
    "Extrae SOLO estos dos campos del comprobante:\n"
    "1. cuenta_destino: número de cuenta, CI, teléfono o identificador "
    "   de la cuenta DESTINO (a quien se transfirió el dinero)\n"
    "2. monto: importe total pagado en bolivianos (solo el número)\n\n"
    'Responde ÚNICAMENTE con JSON válido sin texto adicional:\n'
    '{"cuenta_destino":"XXXX","monto":35.0}\n'
    "Si no puedes leer un campo con certeza, usa null para ese campo."
)


def analyze_comprobante(image_path: str) -> dict:
    """
    Reads a comprobante image and returns:
    {"cuenta_destino": str|None, "monto": float|None, "error": str|None}
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"cuenta_destino": None, "monto": None, "error": "ANTHROPIC_API_KEY no configurada"}

    if not os.path.exists(image_path):
        return {"cuenta_destino": None, "monto": None, "error": "Imagen no encontrada"}

    try:
        import anthropic

        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )

        text = resp.content[0].text.strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            return {
                "cuenta_destino": str(data.get("cuenta_destino") or "").strip() or None,
                "monto": float(data["monto"]) if data.get("monto") is not None else None,
                "error": None,
            }
        return {"cuenta_destino": None, "monto": None, "error": "Respuesta no parseable"}

    except Exception as e:
        logger.error(f"Vision analysis error: {e}")
        return {"cuenta_destino": None, "monto": None, "error": str(e)}
