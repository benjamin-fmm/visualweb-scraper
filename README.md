# visualweb-scraper
Herramienta de scraping y análisis documental para sitios web personales desarrollada en el contexto de una investigación de Seminario en diseño.

- Autor: Benjamín Martínez
- Año: 2025
- Contexto: Proyecto de Seminario — Carrera de Diseño
- Profesor guía: Jacob Bustamante

### Descripción general del proyecto

Este repositorio contiene las herramientas desarrolladas durante mi investigación de Seminario, cuyo propósito inicial consistía en explorar rasgos visuales, estructurales y expresivos de la web independiente contemporánea (especialmente dentro de Neocities).

Durante el proceso, emergió la necesidad de construir un sistema capaz de extraer datos en masa desde un corpus amplio de páginas web personales.
Esto dio origen a una herramienta digital que se divide en dos partes:

- Scraping estructural (metadatos, estilo css, presencia de .gif, idioma, texto visible, atributos HTML)
- Scraping visual (captura de pantalla, paleta de color, proporciones de color, mapa de saliencia)
- Normalización de datos para análisis documental (explicabilidad y visualización)

El proyecto evolucionó, tomando una fuerte gravitación hacia el aspecto metodológico que abría esta herramienta.
Este repositorio documenta la herramienta, su código y muestras de salida.

## Objetivo de la herramienta

Proveer un pipeline que permita analizar corpus grandes de páginas web indie mediante extracción automatizada, especialmente útil en metodologías de:

- análisis documental
- estudios de diseño web personal
- estética digital
- estudios de la web independiente

### Características principales

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
