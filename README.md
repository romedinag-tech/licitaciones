# 📡 Radar de Licitaciones — Medina Consultoría SpA

Descarga automáticamente las licitaciones **activas** de la [API de Mercado Público (ChileCompra)](https://api.mercadopublico.cl), las filtra según el perfil de servicios de Medina Consultoría (transporte, movilidad, IMIV/vialidad, demanda/EOD, planificación urbana, puertos/comercio exterior y datos/analítica) y las publica en un sitio web filtrable.

**Sitio:** https://romedinag-tech.github.io/licitaciones/

## Cómo funciona

1. `radar_mp.py` consulta las licitaciones activas, descarta obras/insumos/servicios operativos, puntúa cada una según categorías del perfil y guarda el detalle en `data/`.
2. El sitio (`index.html`) lee `data/resultados.json` y `data/meta.json` y muestra las oportunidades con buscador, filtros por categoría/región y orden por relevancia o fecha de cierre.
3. GitHub Actions (`.github/workflows/actualizar.yml`) ejecuta el radar **cada día a las 08:00 de Chile** y hace commit de los datos actualizados.

## Configuración (una sola vez)

### 1. Ticket de la API como secret
El ticket personal de Mercado Público se guarda como **secret**, nunca en el código:

`Settings → Secrets and variables → Actions → New repository secret`
- **Name:** `MP_TICKET`
- **Value:** tu ticket

Sin secret, el radar usa el ticket público de pruebas (limitado y lento).

### 2. Activar GitHub Pages
`Settings → Pages → Source: Deploy from a branch → Branch: main / (root)`

### 3. Permisos de Actions
`Settings → Actions → General → Workflow permissions → Read and write permissions`

## Ejecución local (opcional)

```bash
cp .env.example .env      # y pega tu ticket en MP_TICKET
python radar_mp.py        # escribe data/resultados.json, resultados.csv y meta.json
```

Abre `index.html` con un servidor local (por ejemplo `python -m http.server`) para verlo.

## Descargar antecedentes (bases y anexos) a tu PC

El sitio corre en la nube y **no puede** escribir en tu computador, así que la
descarga de antecedentes es un script **local**: `descargar_antecedentes.py`.
Usa tu Chrome real para abrir cada ficha, entrar a Anexos y bajar cada archivo
con el botón individual **"Ver Anexo"** (que el portal entrega sin captcha).
Los guarda en `C:/Users/Rodrigo/Análisis RMG/Licitaciones/<código>/`.

**Instalación (una sola vez):**
```bash
pip install playwright
playwright install chromium
```
(y tener Google Chrome instalado)

**Uso:** doble clic en **`Descargar antecedentes.bat`**, o por consola:
```bash
python descargar_antecedentes.py                # todas las del dashboard
python descargar_antecedentes.py 619284-2-LP26  # solo esos códigos
python descargar_antecedentes.py --force        # re-descarga aunque ya exista
```
Mientras corre se abre una ventana de Chrome (no la cierres). La carpeta de
destino se cambia con la variable de entorno `RADAR_DESTINO`.

> El captcha de "descargar todos" **no** se toca; se usa solo la descarga
> por-archivo, que es pública y sin barrera.

## Analizador de bases (local)

Una vez descargados los antecedentes, `analizar_bases.py` (+ **`Analizar bases.bat`**)
lee los PDF/DOCX/ZIP de cada licitación, extrae el texto, detecta las secciones y
clasifica los **puntos clave** (plazos, garantías, presupuesto, criterios de
evaluación, tareas/alcance, entregables, multas, equipo). Genera en la carpeta de
licitaciones un **`Analizador de Bases.html`** con la estética del dashboard, que:

- Índice hipervinculado por licitación → documento → secciones.
- Lector con navegación y panel de **puntos clave** (salta a la sección).
- **Destacar tareas**: seleccionas texto o un punto clave → se guarda como elemento
  importante **en tu navegador** (privado), por documento. Exportable a Markdown.
- Marca los PDF **escaneados** (sin capa de texto) que requieren OCR.

**Instalación (una sola vez):** `pip install pymupdf python-docx`
**Uso:** doble clic en `Analizar bases.bat` (procesa y abre el visor).

## Personalizar el filtro
Las categorías, pesos y palabras de exclusión están en el diccionario `CATEGORIAS` y la expresión `EXCLUIR` al inicio de `radar_mp.py`. Ajusta ahí para afinar qué licitaciones aparecen.
