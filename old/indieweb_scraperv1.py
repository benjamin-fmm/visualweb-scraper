#!/usr/bin/env python3
"""
indieweb_scraper.py

Scraper general que toma un archivo de texto con URLs (una por línea) y extrae:
- title
- meta description
- meta keywords
- texto visible (sin scripts/styles)
- idioma detectado (langdetect)
- background-color y font-family encontrados en inline styles y CSS linked
- detección de gifs, "botones" (imágenes 88x31 o nombres típicos), sonidos, cursores personalizados
- guarda resultados en CSV o Excel (.xlsx)

Uso (ejemplo):
  python neocities_scraper.py --input urls.txt --output resultado.xlsx --format xlsx --delay 1.0

Notas:
- Respeta robots.txt por host (si robots.txt bloquea la ruta, omite el URL y lo registra).
- Añade delays entre requests para no sobrecargar servidores.
- Si no tienes instalada alguna dependencia (p. ej. langdetect, pandas, openpyxl),
  instálalas con pip:
    pip install requests beautifulsoup4 langdetect pandas openpyxl cssutils lxml
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
import cssutils  # para parsear reglas CSS
import pandas as pd

# reproducibilidad para langdetect
DetectorFactory.seed = 0

# Config logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

USER_AGENT = "NeoScraper/1.0 (+https://example.com)"
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

def detect_language(text):
    if not text or len(text) < 30:
        return ""
    try:
        lang = detect(text)
        return lang
    except LangDetectException:
        return ""

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

def find_buttons_and_blinkies(soup, base_url):
    candidates = []
    # buscar imágenes con tamaño 88x31 (atributos width/height o en class/style)
    for img in soup.find_all("img"):
        src = img.get("src","")
        if not src:
            continue
        full = urljoin(base_url, src)
        w = img.get("width") or img.get("data-width") or ""
        h = img.get("height") or img.get("data-height") or ""
        try:
            if w and h and (int(w) == 88 and int(h) == 31):
                candidates.append(full)
        except:
            pass
        filename = os.path.basename(src).lower()
        if any(k in filename for k in ("button","blink","badge","88x31","88-31")):
            candidates.append(full)
    # también revisar inline styles con background-image que apunten a badge/button
    for tag in soup.find_all(style=True):
        s = tag.get("style","").lower()
        if "background" in s and ("button" in s or "badge" in s):
            m = re.search(r"url\(['\"]?(.*?)['\"]?\)", s)
            if m:
                candidates.append(urljoin(base_url, m.group(1)))
    return list(dict.fromkeys(candidates))

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

def parse_css_for_properties(css_text):
    bg_colors = set()
    fonts = set()
    cursors = set()
    try:
        sheet = cssutils.parseString(css_text)
        for rule in sheet:
            if rule.type == rule.STYLE_RULE:
                for p in rule.style:
                    name = p.name.lower()
                    val = p.value
                    if name in ("background","background-color","background-image"):
                        m = re.search(r"(#(?:[0-9a-fA-F]{3,8})|rgb[a]?\([^\)]+\)|[a-zA-Z]+)", val)
                        if m:
                            bg_colors.add(m.group(1))
                    if name in ("font-family","font"):
                        fonts.add(val)
                    if "cursor" in name or "cursor:" in val:
                        cursors.add(val)
    except Exception as e:
        logging.debug(f"cssutils parse error: {e}")
    return list(bg_colors), list(fonts), list(cursors)

def detect_font_family(font_list):
    keywords = ["comic", "courier", "times", "arial", "verdana", "georgia", "monospace", "serif", "sans-serif"]
    fonts_l = " ".join(font_list).lower() if font_list else ""
    for k in keywords:
        if k in fonts_l:
            return k
    if font_list:
        first = font_list[0].split(",")[0].strip().strip("'\"")
        return first
    return ""

def extract_basic_styles(soup, base_url, session):
    inline_css = styles_from_style_tags_and_inline(soup)
    linked_css = fetch_linked_css(soup, base_url, session)
    css_all = "\n".join([inline_css, linked_css])
    bg_colors, fonts, cursors = parse_css_for_properties(css_all)
    font_family = detect_font_family(fonts)
    cursor_custom = len(cursors) > 0 or ('cursor:' in css_all)
    return bg_colors, font_family, cursor_custom, fonts, cursors

def process_url(url, session):
    result = {
        "url": url,
        "title": "",
        "meta_description": "",
        "keywords": "",
        "language": "",
        "background_colors": [],
        "font_family": "",
        "font_list": [],
        "cursor_custom": False,
        "has_gif": False,
        "gifs": [],
        "has_buttons": False,
        "buttons": [],
        "has_sounds": False,
        "sounds": [],
        "visible_text": "",
        "error": "",
        "tag": ""
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
        result["language"] = detect_language(text)

        gifs = find_gifs(soup, base)
        result["gifs"] = gifs
        result["has_gif"] = len(gifs) > 0

        buttons = find_buttons_and_blinkies(soup, base)
        result["buttons"] = buttons
        result["has_buttons"] = len(buttons) > 0

        sounds = find_sounds(soup, base)
        result["sounds"] = sounds
        result["has_sounds"] = len(sounds) > 0

        bg_colors, font_family, cursor_custom, fonts, cursors = extract_basic_styles(soup, base, session)
        result["background_colors"] = bg_colors
        result["font_family"] = font_family
        result["font_list"] = fonts
        result["cursor_custom"] = cursor_custom

    except Exception as e:
        logging.exception(f"Error procesando {url}: {e}")
        result["error"] = str(e)

    return result

def save_results_csv(rows, output_path):
    fieldnames = [
        "url","title","meta_description","keywords","language",
        "background_colors","font_family","font_list","cursor_custom",
        "has_gif","gifs","has_buttons","buttons","has_sounds","sounds",
        "visible_text","error","tag"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            out = {k: r.get(k,"") for k in fieldnames}
            for k in ("background_colors","font_list","gifs","buttons","sounds"):
                if isinstance(out.get(k), (list,tuple)):
                    out[k] = " | ".join(out[k])
            writer.writerow(out)

def save_results_xlsx(rows, output_path):
    df = pd.DataFrame(rows)
    for col in ["background_colors","font_list","gifs","buttons","sounds"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: " | ".join(v) if isinstance(v, (list,tuple)) else (v or ""))
    df.to_excel(output_path, index=False)

def main():
    parser = argparse.ArgumentParser(description="Neocities / general web scraper basado en lista de URLs")
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
        # permitir input "url <TAB> tag" opcional
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
