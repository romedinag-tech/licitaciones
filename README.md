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

## Personalizar el filtro
Las categorías, pesos y palabras de exclusión están en el diccionario `CATEGORIAS` y la expresión `EXCLUIR` al inicio de `radar_mp.py`. Ajusta ahí para afinar qué licitaciones aparecen.
