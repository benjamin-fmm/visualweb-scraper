#!/usr/bin/env python3
"""
sample_neocities_2020_2022_es.py

Muestrea páginas aleatoriamente en https://neocities.org/browse,
consulta /api/info?sitename=... y guarda hasta 20 sitios por año (2020-2022),
pero solo si su idioma detectado es español.

Usa langdetect sobre título+descripción para estimar idioma.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import urllib.robotparser
import time, random, csv, logging, sys
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0  # asegura reproducibilidad

# ---------- CONFIG ----------
BASE_BROWSE = "https://neocities.org/browse"
API_INFO = "https://neocities.org/api/info?sitename={}"
OUTPUT_CSV = "neocities_sample_2020_2022_es.csv"
USER_AGENT = "SampleBot/1.0 (+https://example.com) Python/requests"
REQUEST_TIMEOUT = 15
DELAY_MIN = 1.0
DELAY_MAX = 3.0
TARGET_PER_YEAR = 20
YEARS = (2020, 2021, 2022)
MAX_ATTEMPTS = 2000
MAX_SITENAME_CHECKS = 5000
SEED = None
# ----------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

if SEED is not None:
    random.seed(SEED)

START_DT = datetime(2020,1,1, tzinfo=timezone.utc)
END_DT = datetime(2022,12,31,23,59,59, tzinfo=timezone.utc)

def robots_allows(path="/browse"):
    parsed = urlparse(BASE_BROWSE)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception as e:
        logging.warning(f"No se pudo leer robots.txt ({robots_url}): {e}. Procede con precaución.")
        return False
    allowed = rp.can_fetch(USER_AGENT, path)
    logging.info(f"robots.txt permite '{path}'? -> {allowed}")
    return allowed


def get_soup(url, tries=3):
    for i in range(tries):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logging.warning(f"Error GET {url}: {e} (int {i+1}/{tries})")
            time.sleep(1 + i)
    return None


def estimate_max_pages():
    soup = get_soup(BASE_BROWSE)
    if not soup:
        logging.warning("No se pudo obtener /browse para estimar páginas. Usando valor por defecto 2000.")
        return 2000

    last_page = None
    for a in soup.select("a"):
        txt = (a.text or "").strip()
        href = a.get("href","")
        if txt.isdigit():
            try:
                n = int(txt)
                if last_page is None or n > last_page:
                    last_page = n
            except:
                pass
        if a.get("rel") and "last" in a.get("rel"):
            if "page=" in href:
                try:
                    p = int(href.split("page=")[-1].split("&")[0])
                    last_page = max(last_page or 0, p)
                except:
                    pass

    if last_page:
        logging.info(f"Estimado max pages: {last_page}")
        return last_page

    logging.info("No se detectó paginación explícita. Usando valor por defecto 2000.")
    return 2000


def extract_sitenames_from_browse(soup):
    sitenames = []
    for a in soup.select("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href.startswith("http") and "neocities.org" in href:
            try:
                host = urlparse(href).netloc
                if host.endswith("neocities.org") and "." in host:
                    name = host.split(".")[0]
                    sitenames.append(name)
                    continue
            except:
                pass
        if href.startswith("/~"):
            name = href.split("/~",1)[1].split("/")[0]
            if name:
                sitenames.append(name)
                continue
        if text and " " not in text and len(text) <= 40 and not any(x in href.lower() for x in ("/browse","/tags","/users","/support","/pages")):
            sitenames.append(text)
    seen = set()
    ordered = []
    for s in sitenames:
        if s and s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def get_site_info(sitename):
    url = API_INFO.format(sitename)
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        js = r.json()
        if js.get("result") == "success" and "info" in js:
            return js["info"]
    except Exception as e:
        logging.debug(f"Error al pedir info de {sitename}: {e}")
    return None


def parse_created_at(created_at_str):
    try:
        dt = parsedate_to_datetime(created_at_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def detect_spanish(text):
    if not text:
        return False
    try:
        lang = detect(text)
        return lang == "es"
    except:
        return False

def detect_chile(text):
    """
    Busca menciones a Chile (en mayúsculas o minúsculas).
    Devuelve True si encuentra, False si no.
    """
    if not text:
        return False
    text_lower = text.lower()
    keywords = ["chile", "chilean"]
    return any(kw in text_lower for kw in keywords)


def save_results(rows, filename=OUTPUT_CSV):
    header = ["sitename","url","created_at","year","title","description","chile_flag"]
    write_header = True
    try:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                write_header = False
        except FileNotFoundError:
            write_header = True
        with open(filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if write_header:
                writer.writeheader()
            for r in rows:
                writer.writerow(r)
    except Exception as e:
        logging.error(f"Error guardando CSV: {e}")


def main():
    if not robots_allows("/browse"):
        logging.error("robots.txt NO permite /browse. Abortando.")
        return

    max_pages = estimate_max_pages()
    logging.info(f"Muesteando entre páginas 1 y {max_pages}")

    counts = {y:0 for y in YEARS}
    collected = {y:[] for y in YEARS}
    seen_sitenames = set()

    attempts = 0
    api_calls = 0
    rows_to_save = []

    while attempts < MAX_ATTEMPTS and api_calls < MAX_SITENAME_CHECKS:
        if all(counts[y] >= TARGET_PER_YEAR for y in YEARS):
            logging.info("Se alcanzó el objetivo para todos los años.")
            break

        page = random.randint(1, max_pages)
        browse_url = f"{BASE_BROWSE}?page={page}"
        soup = get_soup(browse_url)
        attempts += 1
        if not soup:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            continue

        sitenames = extract_sitenames_from_browse(soup)
        random.shuffle(sitenames)

        for s in sitenames:
            if api_calls >= MAX_SITENAME_CHECKS:
                break
            if s in seen_sitenames:
                continue
            seen_sitenames.add(s)

            info = get_site_info(s)
            api_calls += 1
            time.sleep(random.uniform(0.2, 0.6))

            if not info:
                continue
            created_at = info.get("created_at")
            if not created_at:
                continue
            dt = parse_created_at(created_at)
            if not dt:
                continue
            year = dt.year

            # -------- FILTRO DE IDIOMA (ESPAÑOL) --------
            text_to_check = (info.get("title","") or "") + " " + (info.get("description","") or "")
            if not detect_spanish(text_to_check):
                continue
            # --------------------------------------------

            if year in YEARS and counts[year] < TARGET_PER_YEAR:
                row = {
                    "sitename": info.get("sitename",""),
                    "url": f"https://{info.get('sitename','')}.neocities.org" if info.get("sitename") else "",
                    "created_at": created_at,
                    "year": year,
                    "title": info.get("title","") if "title" in info else "",
                    "description": info.get("description","") if "description" in info else "",
                    "chile_flag": detect_chile(text_to_check)
                    }
                rows_to_save.append(row)
                collected[year].append(row)
                counts[year] += 1
                logging.info(f"Recolectado ({year}, ES): {row['sitename']} — totals: {counts}")
                if all(counts[y] >= TARGET_PER_YEAR for y in YEARS):
                    break

        if attempts % 20 == 0 and rows_to_save:
            save_results(rows_to_save)
            rows_to_save = []

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    if rows_to_save:
        save_results(rows_to_save)

    logging.info(f"Proceso terminado. Attempts={attempts}, API calls={api_calls}")
    for y in YEARS:
        logging.info(f"Año {y}: encontrados {counts[y]} sitios")
    total = sum(counts.values())
    logging.info(f"Total sitios guardados: {total}. Archivo: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
