#!/usr/bin/env python3
"""
color_scraper_pdf.py
--------------------

Versión extendida de color_scraper que:
- Captura páginas web completas.
- Extrae paletas de color y proporciones.
- Genera un PDF visual con la captura, paleta y porcentajes.

USO:
  python color_scraper_pdf.py --input neo_es_links.txt --output colores.xlsx --format xlsx --colors 5

DEPENDENCIAS:
  pip install playwright pillow numpy scikit-learn pandas openpyxl matplotlib reportlab
  playwright install chromium
"""

import os
import argparse
import asyncio
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS = None  # Evita DecompressionBombWarning por capturas grandes

import warnings
from sklearn.exceptions import ConvergenceWarning
warnings.filterwarnings("ignore", category=ConvergenceWarning)  # Silencia avisos de K-Means

from sklearn.cluster import KMeans
from playwright.async_api import async_playwright
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

# ---------------------- CONFIGURACIÓN ----------------------

SCREENSHOT_DIR = "screenshots"
PALETTE_DIR = "palettes"
PDF_OUTPUT = "resumen_colores.pdf"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(PALETTE_DIR, exist_ok=True)

# ---------------------- FUNCIONES PRINCIPALES ----------------------

async def capture_screenshot(url, output_path):
    """Captura una página completa y la guarda como PNG usando Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        try:
            await page.goto(url, timeout=60000)
            await page.screenshot(path=output_path, full_page=True)
            print(f"[OK] Captura guardada: {output_path}")
        except Exception as e:
            print(f"[ERROR] No se pudo capturar {url}: {e}")
        await browser.close()

def extract_colors(image_path, n_colors=5):
    """Analiza los colores dominantes de una imagen usando K-Means."""
    img = Image.open(image_path).convert("RGB")
    img_small = img.resize((150, 150))
    img_data = np.array(img_small).reshape((-1, 3))

    kmeans = KMeans(n_clusters=n_colors, n_init=10, random_state=42)
    kmeans.fit(img_data)

    colors_rgb = kmeans.cluster_centers_.astype(int)
    counts = np.bincount(kmeans.labels_)
    total = counts.sum()
    proportions = counts / total

    hex_colors = ["#%02x%02x%02x" % tuple(c) for c in colors_rgb]
    return hex_colors, proportions

def create_palette_image(hex_colors, proportions, output_path):
    """Crea una imagen visual con bandas de color proporcionales."""
    width, height = 600, 100
    palette = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(palette)

    start_x = 0
    for hex_color, prop in zip(hex_colors, proportions):
        band_width = int(width * prop)
        end_x = start_x + band_width
        draw.rectangle([start_x, 0, end_x, height], fill=hex_color)
        start_x = end_x

    palette.save(output_path)
    return output_path

def generate_pdf_report(results):
    """Genera un PDF combinando la captura del sitio, su paleta y datos de color."""
    c = canvas.Canvas(PDF_OUTPUT, pagesize=letter)
    width, height = letter
    margin = 40

    y_positions = [height - margin - 20, height / 2 + 30]  # dos fichas por hoja
    i = 0

    for idx, res in enumerate(results):
        y = y_positions[i % 2]  # alterna entre parte superior e inferior de la hoja
        url = res["url"]
        screenshot = res["screenshot"]
        palette = res["palette"]
        colors_list = [res.get(f"color_{j}") for j in range(1, 6) if res.get(f"color_{j}")]
        props_list = [res.get(f"prop_{j}") for j in range(1, 6) if res.get(f"prop_{j}")]

        # Título
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, f"URL: {url}")

        # Imágenes (más pequeñas)
        img_y = y - 30
        try:
            if os.path.exists(screenshot):
                c.drawImage(ImageReader(screenshot), margin, img_y - 140, width=230, height=120, preserveAspectRatio=True, mask='auto')
            if os.path.exists(palette):
                c.drawImage(ImageReader(palette), margin + 250, img_y - 60, width=230, height=50, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print(f"[WARN] No se pudieron agregar imágenes para {url}: {e}")

        # Texto de colores
        c.setFont("Helvetica", 9)
        y_text = img_y - 80
        for col, prop in zip(colors_list, props_list):
            if col:
                c.setFillColor(colors.black)
                c.drawString(margin + 250, y_text, f"{col} - {prop:.1f}%")
                try:
                    c.setFillColor(colors.HexColor(col))
                    c.rect(margin + 400, y_text - 5, 18, 9, fill=1, stroke=0)
                except Exception:
                    pass
                y_text -= 12

        # Si ya se imprimieron dos fichas, salto de página
        if i % 2 == 1 or idx == len(results) - 1:
            c.showPage()
        i += 1

    c.save()
    print(f"\n📄 PDF generado: {PDF_OUTPUT}")

# ---------------------- MAIN ----------------------

async def main():
    parser = argparse.ArgumentParser(description="Scraper visual de colores con PDF.")
    parser.add_argument("--input", "-i", required=True, help="Archivo con URLs (una por línea).")
    parser.add_argument("--output", "-o", required=True, help="Archivo de salida (.csv o .xlsx).")
    parser.add_argument("--format", "-f", choices=["csv", "xlsx"], default="csv", help="Formato de salida.")
    parser.add_argument("--colors", "-c", type=int, default=5, help="Número de colores dominantes a extraer.")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip() and not u.startswith("#")]

    results = []

    for url in urls:
        name = url.replace("https://", "").replace("http://", "").replace("/", "_")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
        palette_path = os.path.join(PALETTE_DIR, f"{name}_palette.png")

        await capture_screenshot(url, screenshot_path)

        if os.path.exists(screenshot_path):
            hex_colors, proportions = extract_colors(screenshot_path, args.colors)
            create_palette_image(hex_colors, proportions, palette_path)

            data = {"url": url, "screenshot": screenshot_path, "palette": palette_path}
            for i, (col, prop) in enumerate(zip(hex_colors, proportions), start=1):
                data[f"color_{i}"] = col
                data[f"prop_{i}"] = round(float(prop) * 100, 2)
            results.append(data)

    df = pd.DataFrame(results)
    if args.format == "xlsx" or args.output.endswith(".xlsx"):
        df.to_excel(args.output, index=False)
    else:
        df.to_csv(args.output, index=False)

    generate_pdf_report(results)
    print(f"\n✅ Análisis completado. Resultados guardados en {args.output} y {PDF_OUTPUT}")

# ---------------------- EJECUCIÓN ----------------------

if __name__ == "__main__":
    asyncio.run(main())
