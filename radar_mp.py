# -*- coding: utf-8 -*-
"""
Radar de licitaciones Mercado Publico — Medina Consultoria SpA.

Descarga las licitaciones activas de la API de ChileCompra, las filtra segun
el perfil de servicios (transporte, movilidad, IMIV/vialidad, demanda/EOD,
planificacion urbana, puertos/comercio exterior, datos/analitica) y escribe
los resultados en data/ para que el sitio (index.html) los muestre.

El ticket se lee de la variable de entorno MP_TICKET. En GitHub Actions se
inyecta desde el secret del repositorio; en local desde un archivo .env
(ignorado por git). Si no hay ticket, usa el ticket publico de pruebas.
"""
import json, re, sys, time, unicodedata, csv, os, datetime
import urllib.request

TEST_TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"

def cargar_ticket():
    t = os.environ.get("MP_TICKET", "").strip()
    if not t:
        # fallback: leer .env local (KEY=VALUE)
        env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.strip().startswith("MP_TICKET"):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
    return t or TEST_TICKET

TICKET = cargar_ticket()
ES_TEST = TICKET == TEST_TICKET
BASE = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

# throttle entre llamadas de detalle (seg). El ticket publico exige mas espera.
THROTTLE = 2.2 if ES_TEST else 0.6
MAX_DETALLE = int(os.environ.get("MP_MAX_DETALLE", "150"))

# --- Perfil: categoria -> (peso, patron regex sobre texto sin tildes en minusculas) ---
CATEGORIAS = {
    "IMIV / vialidad / transito":  (5, r"\bimiv\b|impacto vial|\btransito\b|semafor|vialidad|\bvial(es)?\b|interseccion|senaliz|gestion de trafico"),
    "Transporte / movilidad":      (5, r"transporte publico|movilidad|\bbuses\b|ferroviari|telefer|ciclovia|ciclo.?rutas?|peaton|micromovilidad|plan de transporte|sistema de transporte"),
    "Demanda / EOD / aforos":      (5, r"encuesta origen|origen.?destino|\beod\b|\baforos?\b|conteo|analisis de demanda|flujo vehicular|ocupacion visual|matriz.*viaje"),
    "Planificacion urbana / IPT":  (4, r"plan regulador|\bpladeco\b|plan maestro|plan comunal|instrumento.*planificacion|desarrollo urbano|prefactibilidad|plan de inversion|ordenamiento territorial"),
    "Estudios / consultoria afin": (2, r"estudio de|consultoria|asesoria|diagnostico|modelacion|\bfactibilidad\b|evaluacion social"),
    "Puertos / comercio exterior": (3, r"portuari|puerto de|logistic|comercio exterior|\baduana|exportaci|borde costero"),
    "Datos / GPS / analitica":     (3, r"\bgps\b|big data|analitica de datos|georrefer|\bsig\b|geoespacial|camaras.*(conteo|analisis|inteligencia)"),
}
# Falsos positivos: obras, insumos, servicios operativos no profesionales.
EXCLUIR = re.compile(
    r"transporte escolar|transporte de (residuos|aridos|agua|personal|pasajeros|carga|alimentos|lena|valores|internos|funcionarios)|"
    r"servicio de transporte|arriendo.*(bus|camion|vehicul|maquinaria|van)|adquisicion|suministro|compra de|"
    r"mantencion|conservacion de camino|mejoramiento de (calle|camino|acera|vereda)|construccion|reposicion|obras de|"
    r"demarcacion|pintura|luminaria|semaforo(s)? (nuevo|led|reposicion)|areas verdes|aseo|vigilancia|guardias|"
    r"alimentacion|racion|insumos|repuestos|neumatic|combustible|petroleo|lubricante", re.I)

def sin_tildes(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()

def get(url, intentos=4):
    req = urllib.request.Request(url, headers={"User-Agent": "radar-licitaciones-rmg/1.0"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"    reintento {i+1} ({e})", file=sys.stderr)
            time.sleep(3 + 3 * i)
    return None

def clasificar(texto):
    t = sin_tildes(texto)
    puntaje, cats = 0, []
    for cat, (peso, pat) in CATEGORIAS.items():
        if re.search(pat, t):
            puntaje += peso
            cats.append(cat)
    return puntaje, cats

def fmt_monto(det):
    m = det.get("MontoEstimado")
    mon = det.get("Moneda") or ""
    if not m:
        return ""
    try:
        return f"{float(m):,.0f} {mon}".replace(",", ".")
    except Exception:
        return f"{m} {mon}"

def main():
    modo = "TICKET DE PRUEBA (limitado)" if ES_TEST else "ticket personal"
    print(f"Radar Mercado Publico — usando {modo}")
    data = get(f"{BASE}?estado=activas&ticket={TICKET}")
    if not data or "Listado" not in data:
        sys.exit("No se pudo descargar el listado de licitaciones activas.")
    listado = data["Listado"]
    print(f"  {len(listado)} licitaciones activas en total.")

    candidatas = []
    for lic in listado:
        nombre = lic.get("Nombre", "")
        if EXCLUIR.search(sin_tildes(nombre)):
            continue
        p, cats = clasificar(nombre)
        if p >= 2:
            candidatas.append({**lic, "p": p})
    candidatas.sort(key=lambda x: -x["p"])
    print(f"  {len(candidatas)} candidatas tras filtro por nombre.")
    if len(candidatas) > MAX_DETALLE:
        print(f"  (limito el detalle a las {MAX_DETALLE} de mayor puntaje)")
        candidatas = candidatas[:MAX_DETALLE]

    resultados = []
    for i, c in enumerate(candidatas):
        cod = c["CodigoExterno"]
        print(f"  [{i+1}/{len(candidatas)}] {cod} — {c['Nombre'][:55]}")
        d = get(f"{BASE}?codigo={cod}&ticket={TICKET}")
        time.sleep(THROTTLE)
        det = (d or {}).get("Listado", [{}])[0] if d else {}
        desc = det.get("Descripcion", "") or ""
        p2, cats2 = clasificar(c["Nombre"] + " " + desc)
        comp = det.get("Comprador") or {}
        fch = det.get("Fechas") or {}
        resultados.append({
            "codigo": cod,
            "nombre": c["Nombre"],
            "puntaje": p2 or c["p"],
            "categorias": sorted(set(cats2)),
            "organismo": comp.get("NombreOrganismo", ""),
            "unidad": comp.get("NombreUnidad", ""),
            "region": comp.get("RegionUnidad", ""),
            "tipo": det.get("Tipo", ""),
            "monto": fmt_monto(det),
            "fecha_cierre": (fch.get("FechaCierre") or c.get("FechaCierre") or "")[:16],
            "fecha_publicacion": (fch.get("FechaPublicacion") or "")[:10],
            "descripcion": desc[:900],
            "url": f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={cod}",
        })

    resultados.sort(key=lambda x: (-x["puntaje"], x["fecha_cierre"] or "9"))

    with open(os.path.join(DATA, "resultados.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)
    if resultados:
        cols = ["codigo", "nombre", "puntaje", "organismo", "region",
                "monto", "fecha_cierre", "fecha_publicacion", "url"]
        with open(os.path.join(DATA, "resultados.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(resultados)

    meta = {
        "actualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "total_activas": len(listado),
        "candidatas": len(candidatas),
        "resultados": len(resultados),
        "modo_ticket": "prueba" if ES_TEST else "personal",
        "regiones": sorted({r["region"] for r in resultados if r["region"]}),
        "categorias": list(CATEGORIAS.keys()),
    }
    with open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"Listo: {len(resultados)} licitaciones escritas en data/.")

if __name__ == "__main__":
    main()
