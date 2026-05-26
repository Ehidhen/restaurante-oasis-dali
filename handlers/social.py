"""
Monitor de la página pública de Facebook del restaurante.
Usa mbasic.facebook.com (versión HTML ligera) para detectar nuevas publicaciones
y extraer automáticamente el menú del día (sopa + segundo + bebida).
"""
import hashlib
import logging
import os
import re

import httpx
from bs4 import BeautifulSoup
from telegram.ext import ContextTypes

import config
import database as db

logger = logging.getLogger(__name__)

FB_PAGE_SLUG = os.getenv("FB_PAGE_SLUG", "OasisdeDali")
FB_BASE = "https://mbasic.facebook.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 11; SM-G991B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PROMO_KEYWORDS = [
    "promo", "oferta", "especial", "descuento", "2x", "combo",
    "precio", "bs", "alitas", "frappe", "jugo", "lunes", "martes",
    "miercoles", "jueves", "viernes", "sábado", "domingo"
]

# ── Detección de menú del día ────────────────────────────────────────────────

MENU_TRIGGERS = [
    "menú del día", "menu del dia", "menú de hoy", "menu de hoy",
    "almuerzo del día", "almuerzo de hoy", "plato del día", "plato de hoy",
    "hoy tenemos", "hoy les ofrecemos",
]

_SOUP_KW    = ["sopa", "crema", "consomé", "caldo", "soup", "🍲", "🥣"]
_MAIN_KW    = ["segundo", "plato", "2do", "principal", "🍽", "🍛", "🥩", "🍖", "🍗"]
_DRINK_KW   = ["refresco", "bebida", "jugo", "limonada", "agua", "frappe", "drink", "🥤", "🍹"]


def _extract_line_value(text: str, keywords: list) -> str:
    """Busca la primera línea que contiene una keyword y extrae el valor."""
    for line in text.split("\n"):
        line_s = line.strip()
        line_low = line_s.lower()
        for kw in keywords:
            if kw.lower() in line_low:
                # Remove the keyword + separator (:, -, –, emoji at start)
                val = re.sub(
                    rf"(?i){re.escape(kw)}\s*[:\-–—]?\s*", "", line_s, count=1
                ).strip()
                # Strip leading emojis/symbols
                val = re.sub(
                    r'^[\U0001F300-\U0001FFFF\U00002600-\U000027BF\s\-:]+', "", val
                ).strip()
                if val and len(val) > 3:
                    return val[:120]
    return ""


def detect_menu(text: str) -> dict | None:
    """
    Returns {soup, main_dish, drink} if the post looks like a daily menu,
    or None if it doesn't seem to be a menu post.
    """
    text_low = text.lower()

    # Must have at least one menu trigger OR both a soup+main keyword
    has_trigger = any(t in text_low for t in MENU_TRIGGERS)
    has_soup    = any(k.lower() in text_low for k in _SOUP_KW if k.isascii() or k in text)
    has_main    = any(k.lower() in text_low for k in _MAIN_KW if k.isascii() or k in text)

    if not has_trigger and not (has_soup and has_main):
        return None

    soup      = _extract_line_value(text, _SOUP_KW)
    main_dish = _extract_line_value(text, _MAIN_KW)
    drink     = _extract_line_value(text, _DRINK_KW)

    if not soup and not main_dish:
        return None

    return {"soup": soup, "main_dish": main_dish, "drink": drink}


def _is_promo(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in PROMO_KEYWORDS)


def _extract_price(text: str) -> str:
    """Extrae mención de precio tipo '2x35 Bs', '65 Bs', etc."""
    patterns = [
        r'\d+\s*[xX]\s*\d+\s*[Bb][Ss]',
        r'\d+\s*[Bb][Ss]',
        r'\$\s*\d+',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0).strip()
    return ""


def _post_id(text: str, url: str) -> str:
    """Genera un ID único para un post basado en su contenido/URL."""
    raw = (url or text or "")[:200]
    return hashlib.md5(raw.encode()).hexdigest()[:16]


async def fetch_facebook_posts() -> list[dict]:
    """
    Obtiene las últimas publicaciones de la página pública.
    Retorna lista de dicts: {post_id, content, image_url, post_url, is_promo, price}
    """
    url = f"{FB_BASE}/{FB_PAGE_SLUG}"
    posts = []

    try:
        async with httpx.AsyncClient(
            headers=HEADERS, follow_redirects=True, timeout=20
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"FB fetch returned {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")

            # mbasic.facebook.com structure: posts are in article or div blocks
            # Try multiple selectors for robustness
            post_blocks = (
                soup.find_all("div", attrs={"data-ft": True}) or
                soup.find_all("article") or
                soup.find_all("div", class_=re.compile(r"story|post|feed", re.I))
            )

            if not post_blocks:
                # Fallback: grab all text paragraphs with links
                post_blocks = soup.find_all("div", id=re.compile(r"\d{10,}"))

            for block in post_blocks[:10]:
                text = block.get_text(separator=" ", strip=True)
                if len(text) < 10:
                    continue

                # Find post link
                link = block.find("a", href=re.compile(r"/story|/posts|/permalink"))
                post_url = ""
                if link and link.get("href"):
                    href = link["href"]
                    post_url = href if href.startswith("http") else FB_BASE + href

                # Find image
                img = block.find("img", src=re.compile(r"http"))
                image_url = img["src"] if img else ""

                pid = _post_id(text, post_url)
                posts.append({
                    "post_id": pid,
                    "content": text[:500],
                    "image_url": image_url,
                    "post_url": post_url or url,
                    "is_promo": _is_promo(text),
                    "price": _extract_price(text),
                })

    except Exception as e:
        logger.error(f"Error al obtener página FB: {e}")

    return posts


async def job_monitor_facebook(ctx: ContextTypes.DEFAULT_TYPE):
    """Job periódico — detecta nuevas publicaciones y notifica."""
    posts = await fetch_facebook_posts()
    if not posts:
        return

    new_posts = []
    for p in posts:
        is_new = db.save_social_post(
            post_id=p["post_id"],
            content=p["content"],
            image_url=p["image_url"],
            post_url=p["post_url"],
        )
        if is_new:
            new_posts.append(p)

    if not new_posts:
        return

    # Notificar al equipo
    oasis = db.get_restaurant("oasis")
    for p in new_posts:
        promo_flag = "🚨 *PROMO DETECTADA*" if p["is_promo"] else "📢 *Nueva publicación*"
        price_str = f"\n💰 Precio detectado: *{p['price']}*" if p["price"] else ""

        msg = (
            f"{promo_flag} en la página oficial\n\n"
            f"📝 {p['content'][:300]}\n"
            f"{price_str}\n\n"
            f"🔗 Ver publicación: {p['post_url']}\n\n"
            f"Para agregar al sistema:\n"
            f"`/nueva_promo Nombre | {p['price'] or 'Precio'} | Descripción`"
        )

        # Auto-registrar si parece promo
        if p["is_promo"] and p["price"]:
            content_short = p["content"][:60].strip()
            db.add_promo(oasis["id"], content_short, p["price"],
                         source="facebook", image_url=p["image_url"])
            msg += f"\n\n✅ _Registrada automáticamente como promo_"

        # Auto-actualizar menú si detectamos sopa + segundo
        menu_data = detect_menu(p["content"])
        if menu_data:
            for rest_name in ["oasis", "dali"]:
                rest = db.get_restaurant(rest_name)
                db.update_menu_dishes(
                    rest["id"],
                    soup=menu_data["soup"],
                    main_dish=menu_data["main_dish"],
                    drink=menu_data["drink"],
                    updated_by="Facebook Auto",
                )
            soup_str = menu_data["soup"] or "—"
            main_str = menu_data["main_dish"] or "—"
            drink_str = menu_data["drink"] or "—"
            msg += (
                f"\n\n🍲 *Menú detectado y actualizado automáticamente*\n"
                f"Sopa: {soup_str}\n"
                f"Segundo: {main_str}\n"
                f"Bebida: {drink_str}\n"
                f"_(El precio lo registra caja con /precio)_"
            )

        all_ids = (
            config.ADMIN_IDS |
            config.OASIS_SUPERVISOR_IDS | config.OASIS_CHIEF_IDS |
            config.DALI_SUPERVISOR_IDS  | config.DALI_CHIEF_IDS
        )
        for tid in all_ids:
            try:
                await ctx.bot.send_message(
                    chat_id=tid, text=msg, parse_mode="Markdown",
                    disable_web_page_preview=False
                )
            except Exception as e:
                logger.debug(f"No entregado a {tid}: {e}")

        db.mark_post_notified(p["post_id"])


def get_latest_posts_summary() -> list[dict]:
    """Para el panel web: últimos 3 posts detectados."""
    rows = db.get_latest_social_posts(3)
    return [dict(r) for r in rows]
