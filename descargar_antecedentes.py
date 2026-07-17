# -*- coding: utf-8 -*-
"""
Descargador de antecedentes (bases y anexos) de las licitaciones del radar.

Corre LOCALMENTE en tu PC (la nube no puede escribir en tu disco). Usa tu
Chrome real vía Playwright para abrir cada ficha de Mercado Publico, entrar a
Anexos y descargar cada archivo con el boton individual "Ver Anexo" — que el
portal entrega SIN captcha (la ruta por-archivo es publica y no tiene barrera;
el captcha solo esta en "descargar todos" y ese NO se toca).

Los archivos se guardan en:  <DESTINO>/<codigo> - <nombre corto>/

Requisitos (instalacion unica):
    pip install playwright
    playwright install chromium        (y tener Google Chrome instalado)

Uso:
    python descargar_antecedentes.py                # todas las del dashboard
    python descargar_antecedentes.py 619284-2-LP26  # solo esos codigos
    python descargar_antecedentes.py --force        # re-descarga aunque exista
"""
import sys, os, re, time, json, pathlib, urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8")   # simbolos/tildes en consola Windows
except Exception:
    pass

# --- Configuracion ---
DESTINO = pathlib.Path(os.environ.get(
    "RADAR_DESTINO",
    pathlib.Path.home() / "Análisis RMG" / "Licitaciones"))
FUENTE = "https://romedinag-tech.github.io/licitaciones/data/resultados.json"
PERFIL = str(pathlib.Path.home() / "pw_chrome_profile")   # perfil dedicado de Chrome
PAUSA = 1.2            # segundos entre archivos (trato gentil al portal)
PAUSA_LIC = 2.5       # segundos entre licitaciones

def limpia(s, n=45):
    s = re.sub(r"[\\/:*?\"<>|]+", " ", s or "").strip()
    return (s[:n]).strip()

def lista_licitaciones(args):
    codigos = [a for a in args if not a.startswith("-")]
    if codigos:
        return [{"codigo": c, "nombre": ""} for c in codigos]
    try:
        with urllib.request.urlopen(FUENTE + "?_=" + str(int(time.time())), timeout=40) as r:
            data = json.load(r)
    except Exception:
        local = pathlib.Path(__file__).parent / "data" / "resultados.json"
        data = json.load(open(local, encoding="utf-8"))
    return [{"codigo": x["codigo"], "nombre": x.get("nombre", "")} for x in data]

def main():
    args = sys.argv[1:]
    force = "--force" in args
    lics = lista_licitaciones(args)
    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {DESTINO}")
    print(f"{len(lics)} licitaciones a revisar.\n")

    from playwright.sync_api import sync_playwright
    total = 0
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PERFIL, channel="chrome", headless=False, accept_downloads=True,
            args=["--disable-blink-features=AutomationControlled"])
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        for i, lic in enumerate(lics, 1):
            cod = lic["codigo"]
            carpeta = DESTINO / f"{cod} - {limpia(lic['nombre'])}".strip(" -")
            if carpeta.exists() and any(carpeta.iterdir()) and not force:
                print(f"[{i}/{len(lics)}] {cod}: ya descargada, se omite.")
                continue
            print(f"[{i}/{len(lics)}] {cod}: {lic['nombre'][:50]}")
            try:
                pg.goto(f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={cod}",
                        wait_until="domcontentloaded", timeout=60000)
                ico = pg.query_selector("#imgAdjuntos")
                if not ico:
                    print("     sin icono de adjuntos, se omite."); continue
                try:
                    with pg.expect_popup(timeout=20000) as pi:
                        ico.click()
                    an = pi.value
                except Exception:
                    print("     no se pudo abrir la ventana de anexos (ficha con otro formato), se omite.")
                    continue
                an.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(2.5)
                botones = an.query_selector_all("input[id^='DWNL_grdId_ctl'][id$='_search']")
                if not botones:
                    print("     no hay anexos publicados."); an.close(); continue
                carpeta.mkdir(parents=True, exist_ok=True)
                bajados = 0
                for b in botones:
                    try:
                        with an.expect_download(timeout=30000) as di:
                            b.click()
                        d = di.value
                        d.save_as(str(carpeta / d.suggested_filename))
                        bajados += 1; total += 1
                        print(f"     OK  {d.suggested_filename}")
                        time.sleep(PAUSA)
                    except Exception as e:
                        print(f"     -- un archivo fallo: {str(e)[:70]}")
                print(f"     {bajados} archivo(s) en {carpeta.name}")
                an.close()
            except Exception as e:
                print(f"     ERROR con {cod}: {str(e)[:90]}")
            time.sleep(PAUSA_LIC)
        ctx.close()
    print(f"\nListo. {total} archivo(s) descargado(s) en {DESTINO}")

if __name__ == "__main__":
    main()
