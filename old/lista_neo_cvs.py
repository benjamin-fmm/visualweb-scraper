#!/usr/bin/env python3
"""
Extrae datos de sitios de Neocities listados en un CSV con columnas Tag,URL.
Consulta la API oficial de Neocities para obtener información del sitio.
Guarda un archivo CSV con sitename, url, tag, fecha de creación, año y título.

Uso:
  python lista_neo_tags.py
"""

import requests
import csv
import time
import logging
from datetime import datetime

INPUT_FILE = "neocities_links_tags.csv"      # CSV con columnas: Tag,URL
OUTPUT_FILE = "neocities_sites_info.csv"     # Archivo de salida
USER_AGENT = "NeoInfoBot/1.0 (+https://example.com)"
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_CALLS = 1.0   # segundos, para ser amable con la API

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def get_sitename(url):
    return url.split("//")[-1].split(".")[0]

def fetch_site_info(sitename):
    api_url = f"https://neocities.org/api/info?sitename={sitename}"
    try:
        r = session.get(api_url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        js = r.json()
        if js.get("result") == "success":
            return js.get("info", {})
    except Exception as e:
        logging.warning(f"Error consultando {sitename}: {e}")
    return {}

def main():
    results = []
    with open(INPUT_FILE, newline="", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            url = row["URL"]
            tag = row["Tag"]
            sitename = get_sitename(url)

            info = fetch_site_info(sitename)
            time.sleep(DELAY_BETWEEN_CALLS)

            created_at = info.get("created_at", "")
            year = ""
            if created_at:
                try:
                    year = datetime.fromisoformat(created_at.replace("Z", "+00:00")).year
                except Exception:
                    pass

            results.append({
                "sitename": sitename,
                "url": url,
                "tag": tag,
                "created_at": created_at,
                "year": year,
                "title": info.get("title", "")
            })

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as outfile:
        fieldnames = ["sitename", "url", "tag", "created_at", "year", "title"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    logging.info(f"Archivo generado: {OUTPUT_FILE} con {len(results)} filas")

if __name__ == "__main__":
    main()