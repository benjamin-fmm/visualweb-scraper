#!/usr/bin/env python3
"""
webscraper_v7.py

Versión extendida del scraper original, con soporte adicional para:
- Extracción de fecha de creación (desde metadatos o API de Neocities)
- Detección de plataforma/host (Neocities, GitHub Pages, Netlify, Vercel, WordPress, Blogger, etc.)
Mantiene todas las funciones originales (detección de gifs, botones, sonidos, cursores, background colors, etc.).

USO
    python indiescraper_v7.py -i linktest.txt -o resultados.xlsx -f xlsx -d 1.0
DEPENDENCIAS
    pip install requests beautifulsoup4 lxml langdetect tinycss2 cssutils pandas openpyxl tldextract
"""

import argparse
import csv
import time
import re
import os
import logging
from urllib.parse import urlparse, urljoin
import urllib.robotparser
import requests
from bs4 import BeautifulSoup, Comment
from langdetect import detect, DetectorFactory, LangDetectException

import tinycss2
import cssutils
import pandas as pd

# reproducibilidad para langdetect
DetectorFactory.seed = 0

# Config logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

USER_AGENT = "IndieScraper/1.0 (+https://example.com)"
REQUEST_TIMEOUT = 15

# Helpers

def read_input_file(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    return lines

def can_fetch_url(url, user_agent=USER_AGENT):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logging.warning(f"No se pudo leer robots.txt para {parsed.netloc}: {e}. Asumiendo permitido.")
        return True

def get_root_url(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

def fetch_url(url, session, timeout=REQUEST_TIMEOUT):
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    r = session.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r

def extract_title(soup):
    t = soup.title
    if t and t.string:
        return t.string.strip()
    # fallback: meta property og:title
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og.get("content").strip()
    return ""

def extract_meta(soup, name):
    tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag.get("content").strip()
    # try case-insensitive
    for m in soup.find_all("meta"):
        if m.get("name") and m.get("name").lower() == name.lower() and m.get("content"):
            return m.get("content").strip()
    return ""

def visible_text_from_soup(soup):
    # Remove scripts/styles/comments
    for element in soup(["script","style","noscript","iframe","svg","canvas","header","footer","nav"]):
        element.decompose()
    # remove comments
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    for c in comments:
        c.extract()
    text = soup.get_text(separator="\n")
    # compactar múltiples saltos de línea
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)

# ------------------------- Avanzado: Detección de idioma con probabilidades -------------------------

from langdetect import detect_langs

def detect_language_profile(text):
    """
    Analiza el idioma de un texto y devuelve:
      - idioma principal (string)
      - probabilidad del idioma principal (float)
      - lista de idiomas detectados (string separados por ' | ')
      - si el texto parece multilingüe (bool)
    
    Usa detect_langs() para estimar probabilidades y filtra palabras de préstamo.
    """
    if not text or len(text) < 50:
        return "", 0.0, "", False

    # limitar a un tamaño razonable
    text = text[:8000]
    text_lower = text.lower()

    # Filtrar préstamos comunes del inglés que confunden al detector
    borrowed_words = [
        "home", "about", "contact", "portfolio", "index", "welcome",
        "update", "blog", "link", "back", "gallery", "by", "from",
        "guestbook", "shoutbook", "pet", "webring", "webpage", "post",
        "webmaster"
    ]
    for w in borrowed_words:
        text_lower = text_lower.replace(f" {w} ", " ")

    try:
        lang_probs = detect_langs(text_lower)
        # lang_probs es algo como: [es:0.87, en:0.13]
        langs_detected = [(str(l.lang), float(l.prob)) for l in lang_probs]
        langs_detected.sort(key=lambda x: x[1], reverse=True)

        primary_lang, confidence = langs_detected[0]
        all_langs = " | ".join([l for l, p in langs_detected if p > 0.05])
        is_multilingual = len([p for l, p in langs_detected if p > 0.15]) > 1

        # Heurísticas para corregir falsos positivos
        if primary_lang in ("sw", "pt", "no", "ca") and any(w in text_lower for w in [" de ", " la ", " el ", " que ", " los "]):
            primary_lang = "es"
        if primary_lang not in ("es", "en") and any(w in text_lower for w in [" the ", " and ", " to ", " of "]):
            primary_lang = "en"

        return primary_lang, confidence, all_langs, is_multilingual

    except LangDetectException:
        return "", 0.0, "", False

# ------------------------- Fecha de creación y última actualización -------------------------

from datetime import datetime, timezone
import email.utils

def format_datetime_iso(date_str, include_gmt=True):
    """
    Normaliza una fecha de texto al formato dd/mm/yyyy HH:MM (24h)
    Acepta ISO, RFC2822 y otros formatos comunes de la web.
    """
    if not date_str:
        return ""

    from datetime import datetime, timezone
    import email.utils

    parsed = None

    # Intentar parsear como ISO estándar
    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    # Intentar parsear como RFC2822
    if not parsed:
        try:
            parsed = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            pass

    if not parsed:
        return date_str  # fallback, sin formato

    # Convertir a UTC/GMT
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc)
    else:
        parsed = parsed.replace(tzinfo=timezone.utc)

    # Devolver en formato 24h
    if include_gmt:
        return parsed.strftime("%d/%m/%Y %H:%M GMT")
    else:
        return parsed.strftime("%d/%m/%Y %H:%M")


def get_creation_date(url, soup):
    """Intenta detectar fecha de creación desde metadatos HTML o API de Neocities"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    creation_raw = ""

    # Si es un sitio de Neocities → usar API pública
    if "neocities.org" in host:
        sitename = host.split(".")[0]
        try:
            api_url = f"https://neocities.org/api/info?sitename={sitename}"
            r = requests.get(api_url, timeout=10)
            js = r.json()
            if js.get("result") == "success":
                creation_raw = js["info"].get("created_at", "")
                if creation_raw:
                    return format_datetime_iso(creation_raw, include_gmt=True)
        except Exception:
            pass

    # Fallback: buscar metadatos comunes
    for tag, attrs in [
        ("meta", {"name": "date"}),
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"itemprop": "dateCreated"}),
        ("time", {"datetime": True}),
    ]:
        t = soup.find(tag, attrs=attrs)
        if t:
            content = t.get("content") or t.get("datetime")
            if content:
                return format_datetime_iso(content, include_gmt=True)

    return ""

def get_last_update_date(url, soup):
    """Intenta detectar fecha de última actualización desde metadatos o API de Neocities"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    update_raw = ""

    # Si es un sitio de Neocities → usar API pública
    if "neocities.org" in host:
        sitename = host.split(".")[0]
        try:
            api_url = f"https://neocities.org/api/info?sitename={sitename}"
            r = requests.get(api_url, timeout=10)
            js = r.json()
            if js.get("result") == "success":
                update_raw = js["info"].get("last_updated", "")
                if update_raw:
                    return format_datetime_iso(update_raw, include_gmt=True)
        except Exception:
            pass

    # Fallback: buscar metadatos comunes
    for tag, attrs in [
        ("meta", {"property": "article:modified_time"}),
        ("meta", {"property": "og:updated_time"}),
        ("meta", {"itemprop": "dateModified"}),
        ("meta", {"name": "last-modified"}),
        ("time", {"itemprop": "dateModified"}),
    ]:
        t = soup.find(tag, attrs=attrs)
        if t:
            content = t.get("content") or t.get("datetime")
            if content:
                return format_datetime_iso(content, include_gmt=True)

    # Fallback final: encabezado HTTP “Last-Modified”
    try:
        r = requests.head(url, timeout=10)
        if "Last-Modified" in r.headers:
            return format_datetime_iso(r.headers["Last-Modified"], include_gmt=True)
    except Exception:
        pass

    return ""


# ------------------------- Nueva: Tags desde API de Neocities -------------------------

def get_neocities_tags(url):
    """Devuelve las etiquetas (tags) del sitio Neocities usando la API pública."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "neocities.org" not in host:
        return []
    sitename = host.split(".")[0]
    try:
        api_url = f"https://neocities.org/api/info?sitename={sitename}"
        r = requests.get(api_url, timeout=10)
        js = r.json()
        if js.get("result") == "success":
            return js["info"].get("tags", [])
    except Exception as e:
        logging.debug(f"No se pudieron obtener tags de Neocities: {e}")
    return []


# ------------------------- Detección de plataforma -------------------------

def detect_platform(url, html_text):
    host = urlparse(url).netloc.lower()
    html_lower = html_text.lower()
    if "neocities.org" in host:
        return "Neocities"
    if "github.io" in host:
        return "GitHub Pages"
    if "netlify.app" in host:
        return "Netlify"
    if "vercel.app" in host:
        return "Vercel"
    if "wordpress.com" in host or "wp-content" in html_lower:
        return "WordPress"
    if "blogspot." in host:
        return "Blogger"
    if "wixsite.com" in host:
        return "Wix"
    if "weebly.com" in host:
        return "Weebly"
    if "glitch.me" in host:
        return "Glitch"
    if "replit.dev" in host or "repl.co" in host:
        return "Replit"
    if "google.com/sites" in html_lower:
        return "Google Sites"
    return "Unknown"

# ------------------------- Funciones de estilo y medios -------------------------

def find_gifs(soup, base_url):
    gifs = []
    for img in soup.find_all("img"):
        src = img.get("src","")
        if not src:
            continue
        full = urljoin(base_url, src)
        if full.lower().endswith(".gif") or ".gif" in full.lower():
            gifs.append(full)
    return list(dict.fromkeys(gifs))

def find_buttons_and_blinkies(soup, base_url, session=None):
    """
    Detecta botones y blinkies en una página HTML.
    Botones: ~88x31 px, 80x15 px
    Blinkies: ~150x20 px
    Usa dimensiones, nombres de archivo y estilos CSS.
    """
    buttons = []
    blinkies = []
    checked_urls = set()

    def classify_by_size(w, h, url):
        try:
            w, h = int(w), int(h)
        except Exception:
            return None

        # Blinkies típicos (más largos y delgados)
        if 120 <= w <= 160 and 18 <= h <= 25:
            blinkies.append(url)
        # Botones típicos (más pequeños y gruesos)
        elif 70 <= w <= 100 and 12 <= h <= 35:
            buttons.append(url)

    # --- Escaneo de etiquetas <img> ---
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src:
            continue
        full = urljoin(base_url, src)
        if full in checked_urls:
            continue
        checked_urls.add(full)

        w = img.get("width") or img.get("data-width")
        h = img.get("height") or img.get("data-height")

        # Clasificar por dimensiones explícitas si existen
        if w and h:
            classify_by_size(w, h, full)
            continue

        # Fallback: intentar obtener tamaño real si es pequeño (requiere PIL)
        if session and full.lower().endswith((".gif", ".png", ".jpg", ".jpeg")):
            try:
                r = session.get(full, stream=True, timeout=5)
                r.raise_for_status()
                from PIL import Image
                from io import BytesIO
                img_obj = Image.open(BytesIO(r.content))
                w, h = img_obj.size
                classify_by_size(w, h, full)
            except Exception:
                pass

        # Clasificación textual por nombre de archivo
        filename = os.path.basename(src).lower()
        if any(k in filename for k in ("button", "badge", "btn", "88x31", "80x15")):
            buttons.append(full)
        elif any(k in filename for k in ("blink", "blinkie", "150x20")):
            blinkies.append(full)

    # --- Revisar estilos inline con background-image ---
    for tag in soup.find_all(style=True):
        s = tag.get("style", "").lower()
        if "background" in s and ("button" in s or "badge" in s or "blink" in s):
            m = re.search(r"url\(['\"]?(.*?)['\"]?\)", s)
            if m:
                url_img = urljoin(base_url, m.group(1))
                if "blink" in s or "150x20" in s:
                    blinkies.append(url_img)
                else:
                    buttons.append(url_img)

    # --- Eliminar duplicados conservando orden ---
    buttons = list(dict.fromkeys(buttons))
    blinkies = list(dict.fromkeys(blinkies))

    return buttons, blinkies

def find_sounds(soup, base_url):
    sounds = []
    # audio, embed, bgsound, object with data param
    for tag in soup.find_all(["audio","embed","bgsound","object","source"]):
        src = tag.get("src") or tag.get("data") or tag.get("value") or ""
        if src:
            sounds.append(urljoin(base_url, src))
        if tag.name == "audio":
            for s in tag.find_all("source"):
                if s.get("src"):
                    sounds.append(urljoin(base_url, s.get("src")))
    return list(dict.fromkeys(sounds))

def styles_from_style_tags_and_inline(soup):
    css_texts = []
    # inline style attributes
    for tag in soup.find_all(style=True):
        css_texts.append(tag.get("style",""))
    # <style> tags
    for style in soup.find_all("style"):
        if style.string:
            css_texts.append(style.string)
    return "\n".join(css_texts)

def fetch_linked_css(soup, base_url, session):
    css_contents = []
    for link in soup.find_all("link", rel=lambda x: x and 'stylesheet' in x.lower()):
        href = link.get("href")
        if not href:
            continue
        css_url = urljoin(base_url, href)
        try:
            r = session.get(css_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent":USER_AGENT})
            if r.status_code == 200 and 'text/css' in r.headers.get('Content-Type',''):
                css_contents.append(r.text)
        except Exception as e:
            logging.debug(f"No se pudo traer CSS {css_url}: {e}")
    return "\n".join(css_contents)

# ------------------------- CSS Moderno con tinycss2 + cssutils fallback -------------------------

def parse_css_for_properties_combined(css_text):
    """
    Analiza CSS buscando colores, fuentes, cursores y gradientes.
    Usa primero tinycss2 (CSS3/4) y recurre a cssutils si hay error.
    """
    colors, fonts, cursors = set(), set(), set()
    has_gradients = False
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

    try:
        # --- tinycss2 parse ---
        rules = tinycss2.parse_stylesheet(css_text, skip_comments=True, skip_whitespace=True)
        for rule in rules:
            if rule.type != "qualified-rule":
                continue
            declarations = tinycss2.parse_declaration_list(rule.content)
            for decl in declarations:
                if decl.type != "declaration":
                    continue
                name = decl.lower_name or ""
                value = tinycss2.serialize(decl.value).strip().lower()

                # Colores y gradientes
                if any(x in name for x in ["background", "color", "border"]):
                    if "gradient(" in value:
                        has_gradients = True
                    matches = re.findall(
                        r"(#[0-9a-f]{3,8}|rgb[a]?\([^)]+\)|hsl[a]?\([^)]+\)|var\([^)]+\)|linear-gradient\([^)]+\)|\b[a-z]+\b)",
                        value
                    )
                    for c in matches:
                        colors.add(c.strip())

                # Fuentes
                if "font-family" in name or name == "font":
                    clean_val = re.sub(r"[\"']", "", value)
                    fonts.add(clean_val.strip())

                # Cursores personalizados
                if "cursor" in name and "url(" in value:
                    m = re.search(r"url\(['\"]?(.*?)['\"]?\)", value)
                    if m:
                        cursors.add(m.group(1).strip())

    except Exception as e:
        # --- Fallback con cssutils si tinycss2 falla ---
        sheet = cssutils.parseString(css_text)
        for rule in sheet:
            if rule.type == rule.STYLE_RULE:
                for p in rule.style:
                    name = p.name.lower()
                    val = p.value
                    if name in ("background", "background-color", "background-image"):
                        if "gradient(" in val:
                            has_gradients = True
                        m = re.search(r"(#(?:[0-9a-fA-F]{3,8})|rgb[a]?\([^)]+\)|[a-zA-Z]+)", val)
                        if m:
                            colors.add(m.group(1))
                    if name in ("font-family", "font"):
                        fonts.add(val)
                    if "cursor" in name or "cursor:" in val:
                        cursors.add(val)

    return list(colors), list(fonts), list(cursors), has_gradients


def extract_basic_styles(soup, base_url, session):
    """
    Extrae estilos visuales clave:
    - Colores de fondo / gradientes / variables CSS
    - Fuente principal
    - Cursores personalizados
    Combina inline styles + hojas externas.
    """
    css_texts = []

    # Inline <style> y atributos style=""
    for tag in soup.find_all(style=True):
        css_texts.append(tag.get("style", ""))
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            css_texts.append(style_tag.string)

    # Hojas externas
    for link in soup.find_all("link", rel=lambda x: x and 'stylesheet' in x.lower()):
        href = link.get("href")
        if not href:
            continue
        css_url = urljoin(base_url, href)
        try:
            r = session.get(css_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
            if r.status_code == 200 and 'text/css' in r.headers.get('Content-Type', ''):
                css_texts.append(r.text)
        except Exception as e:
            logging.debug(f"No se pudo traer CSS externo {css_url}: {e}")

    css_all = "\n".join(css_texts)
    bg_colors, fonts, cursors, has_gradients = parse_css_for_properties_combined(css_all)

    # Detectar fuente principal (prioridad a la primera válida)
    def detect_font_family(font_list):
        if not font_list:
            return ""
        keywords = ["comic", "courier", "times", "arial", "verdana", "georgia", "monospace", "serif", "sans-serif"]
        joined = " ".join(font_list).lower()
        for k in keywords:
            if k in joined:
                return k
        return font_list[0].split(",")[0].strip().strip("'\"")

    font_family = detect_font_family(fonts)
    cursor_custom = len(cursors) > 0 or ('cursor:' in css_all)

    return bg_colors, font_family, cursor_custom, fonts, cursors, has_gradients

# ------------------------- Procesamiento -------------------------

def process_url(url, session):
    result = {
        "url": url,
        "title": "",
        "meta_description": "",
        "keywords": "",
        "language": "",
        "language_confidence": 0.0,
        "languages_detected": "",
        "multilingual": False,
        "background_colors": [],
        "font_family": "",
        "font_list": [],
        "cursor_custom": False,
        "cursor_links": [],
        "has_gif": False,
        "gifs": [],
        "has_buttons": False,
        "buttons": [],
        "has_blinkies": False,
        "blinkies": [],
        "has_sounds": False,
        "sounds": [],
        "visible_text": "",
        "error": "",
        "tags_api": [],
        "tag": "",
        "created_at": "",
        "last_updated": "",
        "platform": ""
    }
    try:
        if not can_fetch_url(url):
            result["error"] = "Blocked by robots.txt"
            logging.info(f"Omitido por robots.txt: {url}")
            return result

        r = fetch_url(url, session)
        base = get_root_url(url)
        soup = BeautifulSoup(r.text, "lxml")

        result["title"] = extract_title(soup)
        result["meta_description"] = extract_meta(soup, "description")
        result["keywords"] = extract_meta(soup, "keywords")
        text = visible_text_from_soup(soup)
        result["visible_text"] = (text[:20000])

        primary_lang, confidence, all_langs, is_multi = detect_language_profile(text)
        result["language"] = primary_lang
        result["language_confidence"] = round(confidence, 3)
        result["languages_detected"] = all_langs
        result["multilingual"] = is_multi

        result["created_at"] = get_creation_date(url, soup)
        result["last_updated"] = get_last_update_date(url, soup)

        result["platform"] = detect_platform(url, r.text)
        result["tags_api"] = get_neocities_tags(url)

        gifs = find_gifs(soup, base)
        result["gifs"] = gifs
        result["has_gif"] = len(gifs) > 0

        buttons, blinkies = find_buttons_and_blinkies(soup, base, session)
        result["buttons"] = buttons
        result["has_buttons"] = len(buttons) > 0
        result["blinkies"] = blinkies
        result["has_blinkies"] = len(blinkies) > 0

        sounds = find_sounds(soup, base)
        result["sounds"] = sounds
        result["has_sounds"] = len(sounds) > 0

        bg_colors, font_family, cursor_custom, fonts, cursors, has_gradients = extract_basic_styles(soup, base, session)
        result["background_colors"] = bg_colors
        result["font_family"] = font_family
        result["font_list"] = fonts
        result["cursor_custom"] = cursor_custom
        result["cursor_links"] = cursors
        result["has_gradients"] = has_gradients

    except Exception as e:
        logging.exception(f"Error procesando {url}: {e}")
        result["error"] = str(e)

    return result

# ------------------------- Guardado -------------------------

def save_results_csv(rows, output_path):
    fieldnames = [
        "url","title","tags_api","created_at","last_updated",
        "meta_description","keywords",
        "language","language_confidence","languages_detected","multilingual",
        "background_colors","font_family","font_list","cursor_custom", "has_gradients",
        "has_gif","gifs",
        "has_buttons","buttons",
        "has_blinkies","blinkies",
        "has_sounds","sounds",
        "visible_text","error","platform","tag"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            out = {k: r.get(k, "") for k in fieldnames}
            # convertir listas a texto legible
            for k in ("background_colors","font_list","gifs","buttons","blinkies","sounds","tags_api", "cursor_links"):
                if isinstance(out.get(k), (list,tuple)):
                    out[k] = ", ".join(out[k])
            writer.writerow(out)

def save_results_xlsx(rows, output_path):
    df = pd.DataFrame(rows)
    for col in ["background_colors","font_list","gifs","buttons","blinkies","sounds","tags_api","cursor_links"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: ", ".join(v) if isinstance(v, (list, tuple)) else (v or "")
        )
    df.to_excel(output_path, index=False)

# ------------------------- Main -------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper extendido para webrings e IndieWebs")
    parser.add_argument("--input", "-i", required=True, help="Archivo .txt con URLs (una por línea)")
    parser.add_argument("--output", "-o", required=True, help="Archivo de salida (.csv o .xlsx)")
    parser.add_argument("--format", "-f", choices=("csv","xlsx"), default="csv", help="Formato de salida")
    parser.add_argument("--delay", "-d", type=float, default=1.0, help="Delay entre requests en segundos")
    parser.add_argument("--max", type=int, default=0, help="Máximo de URLs a procesar (0 = todos)")
    args = parser.parse_args()

    urls = read_input_file(args.input)
    if args.max and args.max > 0:
        urls = urls[:args.max]

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    results = []
    for i, line in enumerate(urls, 1):
        if "\t" in line:
            url, tag = [p.strip() for p in line.split("\t",1)]
        else:
            url, tag = line, ""
        logging.info(f"[{i}/{len(urls)}] Procesando: {url} (tag='{tag}')")
        res = process_url(url, session)
        res["tag"] = tag
        results.append(res)
        time.sleep(args.delay)

    out = args.output
    if args.format == "csv" or out.lower().endswith(".csv"):
        save_results_csv(results, out)
    else:
        save_results_xlsx(results, out)

    logging.info(f"Guardado {len(results)} filas en {out}")

if __name__ == "__main__":
    main()