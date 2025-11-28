# visualweb-scraper
Herramienta de scraping y análisis documental para sitios web personales desarrollada en el contexto de una investigación de Seminario en diseño.

Autor: Benjamín Martínez  
Año: 2025  
Contexto: Proyecto de Seminario — Carrera de Diseño  
Profesor guía: Jacob Bustamante

## Descripción general del proyecto

Este repositorio contiene las herramientas desarrolladas durante mi investigación de Seminario, cuyo propósito inicial consistía en explorar rasgos visuales, estructurales y expresivos de la web independiente contemporánea (especialmente dentro de Neocities).

Durante el proceso, emergió la necesidad de construir un sistema capaz de extraer datos en masa desde un corpus amplio de páginas web personales.
Esto dio origen a una herramienta digital que se divide en dos partes:

- Scraping estructural (metadatos, estilo css, presencia de .gif, idioma, texto visible, atributos HTML)
- Scraping visual (captura de pantalla, paleta de color, proporciones de color, mapa de saliencia)
- AMBOS con normalización de datos para análisis documental (explicabilidad y visualización)

El proyecto evolucionó, tomando una fuerte gravitación hacia el aspecto metodológico que abría esta herramienta.
Este repositorio documenta la herramienta, su código y muestras de salida.

### Objetivo de la herramienta (actualmente)

Proveer un pipeline que permita analizar corpus grandes de páginas web indie mediante extracción automatizada, especialmente útil en metodologías de:

- análisis documental
- estudios de diseño web personal
- estética digital
- estudios de la web independiente

## Características principales

Scraper estructural (webscraper_v7.py)

Extrae:

- autor (extraído de la API de Neocities)
- título
- meta descripción
- keywords
- fecha de creación (cuando existe)
- última actualización (cuando existe)
- idioma y multilingüismo (con porcentaje de la fiabilidad de la detección)
- tipografías
- colores declarados en CSS (hexadecimal, rgb o html)
- presencia de gradientes
- detección de cursor custom
- presencia de GIFs, blinkies, botones
- sonidos incrustados
- texto visible
- tags de Neocities (extraídos de la API de Neocities)
- información del hosting (tldextract)

Genera:

- archivo .xslx o .csv según lo especificado con los datos antes mencionados

Scraper visual (color_scraper_v2.py)

Extrae:

- Screenshot (reproducción visual de la página web en base al código bruto)
- Paleta de colores (código hexadecimal, 5 por defecto)
- Proporción de cada color (según pixeles)

Genera:

- Captura de página completa (reconstrucción visual parcial)
- Paleta de color con porcentajes
- Mapa de saliencia visual mediante OpenCV (según capturas obtenidas)
- Clusterización de colores (K-Means)
- Archivo .pdf que combina en un documento lo antes mencionado para un formato más visual más cómodo
- Archivo .xslx o .csv según lo especificado con los códigos y proporciones exactas de la paleta de color de cada página

# Instalación

Este repositorio contiene dos scrapers distintos:

webscraper — Extrae metadatos, estilos, imágenes, sonidos, blinkies, botones, cursores, texto visible, idioma y estructuras básicas.

visualscraper — Captura pantallas, genera paletas de color y crea mapas de saliencia tipo heatmap, más un PDF resumen.

1. Crear entorno virtual (opcional, pero recomendado si es pertinente)
```
python -m venv venv
source venv/bin/activate   # Linux/MacOS
venv\Scripts\activate      # Windows
```
2. Instalar dependencias
```
pip install -r requirements.txt
```
Nota: Playwright requiere una instalación adicional de Chromium:
```
playwright install chromium
```
IMPORTANTE: Versión de Python

La herramienta requiere Python ≤ 3.12

Esto se debe a incompatibilidades conocidas entre numpy, opencv-python y opencv-contrib-python en versiones más recientes.

Se recomienda:
```
python --version
```
Si está por encima de 3.12, crear un entorno:
```
conda create -n visualweb python=3.12
conda activate visualweb
```
o
```
pyenv install 3.12
pyenv local 3.12
```
# Uso

Scraper estructural
python src/webscraper_v7.py

```
python webscraper_v7.py --input urls.txt --output datos.xlsx
```
Argumentos:  
--input → archivo con URLs (una por línea)  
--output → archivo CSV o XLSX generado  

Salida:  
Un CSV/XLSX con columnas de metadatos, estilos (colores, fuentes, gradientes), imágenes especiales (blinkies, botones, etc.), idioma, tags, fechas y más.

Scraper visual
python src/visualscraper_v2.py
```
python visualscraper_v2.py --input urls.txt --output colores.xlsx --format xlsx --colors 5
```
Argumentos:  
--input → archivo de URLs  
--output → archivo CSV/XLSX con resultados  
--colors → número de colores dominantes a extraer  
--format → csv o xlsx

Salida:  
Carpeta screenshots/ → capturas completas de cada web  
Carpeta palettes/ → imagen del cluster de paleta de colores  
Carpeta heatmaps/ → mapa de saliencia (rojo: alta atención, azul: baja atención)  
resumen_colores.pdf → PDF con screenshots + heatmap + paleta + porcentajes para cada link ingresado  
colores.xlsx(.csv) → columnas para cada página web con los códigos hexadecimales y porcentajes de dominancia exactos para cada color

### Notas metodológicas breves

Este proyecto forma parte de un estudio exploratorio que combina análisis documental, herramientas digitales y recolección automatizada de datos. La herramienta está pensada para:

reducir sesgos en la observación  
sistematizar corpus grandes  
facilitar análisis comparativos  
generar datos sólidos para fundamentar un marco teórico futuro  

El repositorio es tanto una herramienta funcional como evidencia del proceso investigativo.
