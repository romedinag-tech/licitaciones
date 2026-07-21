# -*- coding: utf-8 -*-
"""
Radar de licitaciones Mercado Publico — Medina Consultoria SpA.

Descarga las licitaciones activas de la API de ChileCompra y deja SOLO
ESTUDIOS de transporte y planificacion urbana/territorial (la especialidad
de RMG). Descarta obras de infraestructura e inspeccion fiscal de obras.

Regla (sobre nombre + descripcion):
  1. ES_ESTUDIO  -> es un servicio de consultoria/estudio (no una obra).
  2. NO es EXCLUIR -> no es obra ni inspeccion fiscal de infraestructura.
  3. ON_TEMA o de un ORGANISMO CLAVE -> del tema, o de un organismo que
     siempre se vigila (SECTRA, DTPR, DTPM, DIRPLAN, Vialidad, Concesiones,
     SERVIU, o una municipalidad con un PIEP).

El ticket se lee de la variable de entorno MP_TICKET (secret en GitHub
Actions; archivo .env local ignorado por git). Sin ticket usa el de prueba.
"""
import json, re, sys, time, unicodedata, csv, os, datetime
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")  # logs con tildes en cualquier consola
except Exception:
    pass

TEST_TICKET = "F8537A18-6766-4DEF-9E59-426B4FEE2844"

def cargar_ticket():
    t = os.environ.get("MP_TICKET", "").strip()
    if not t:
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

THROTTLE = 2.2 if ES_TEST else 0.6
MAX_DETALLE = int(os.environ.get("MP_MAX_DETALLE", "250"))

# --- Categorias (para etiquetar y puntuar) -> (peso, patron) ---
CATEGORIAS = {
    "IMIV / impacto vial":         (5, r"\bimiv\b|impacto vial|estudio de impacto sobre el sistema de transporte"),
    "Transporte / movilidad":      (5, r"plan de transporte|sistema de transporte|movilidad|transporte publico|\bbuses\b|ferroviari|telefer|ciclovia|ciclo.?rutas?|peaton|micromovilidad"),
    "Demanda / EOD / aforos":      (5, r"encuesta origen|origen.?destino|\beod\b|analisis de demanda|matriz.*viaje|particion modal|modelacion de transporte"),
    "Planificacion urbana / IPT":  (4, r"plan regulador|\bpladeco\b|plan seccional|plan maestro|instrumento.*planificacion|desarrollo urbano|ordenamiento territorial|uso de suelo|plan de inversion"),
    "Espacio publico / PIEP":      (4, r"\bpiep\b|espacio publico|infraestructura de movilidad|aporte.*espacio publico"),
    "Vialidad / transito":         (3, r"\bvialidad\b|\btransito\b|\btrafico\b|gestion de trafico|seguridad vial|estudio vial|gestion vial|interseccion"),
    "Concesiones / logistica":     (3, r"concesion|iniciativa privada|portuari|logistic|comercio exterior"),
    "Datos / analitica":           (2, r"\bgps\b|big data|analitica|georrefer|\bsig\b|geoespacial"),
}

def C(p): return re.compile(p, re.I)

# 1) Es un ESTUDIO / consultoria (servicio intelectual, no una obra).
ESTUDIO = C(r"\bestudio\b|estudios|consultoria|\basesoria\b|diagnostico|levantamiento de informacion|"
            r"plan (de|maestro|regulador|comunal|seccional|estrategico|de desarrollo|de transporte|de movilidad|de inversion)|"
            r"\bpladeco\b|plan regulador|actualizacion del plan|modelacion|prefactibilidad|\bfactibilidad\b|"
            r"evaluacion social|encuesta|origen.?destino|\beod\b|\bimiv\b|impacto vial|"
            r"analisis de demanda|matriz.*viaje|ordenamiento territorial|instrumento de planificacion|\bpiep\b|"
            r"preinversion|pre.?inversion|anteproyecto|alternativas de\s*(pre)?inversion|"
            r"estudio de ingenieria|evaluacion tecnico.?economica|\bep\b")

# 1b) Marcadores FUERTES de estudio (preinversion/planificacion): protegen contra
#     palabras de obra fisica (p.ej. "EP CONSTRUCCION..." es un estudio, no la obra).
ESTUDIO_FUERTE = C(r"preinversion|pre.?inversion|anteproyecto|alternativas de\s*(pre)?inversion|"
                   r"prefactibilidad|\bfactibilidad\b|evaluacion (social|tecnico|economic)|"
                   r"estudio de (preinversion|ingenieria|prefactibilidad|factibilidad|impacto)|"
                   r"plan (maestro|regulador|de transporte|de movilidad|seccional|comunal)|\bpladeco\b|"
                   r"\bimiv\b|impacto vial|origen.?destino|\beod\b|\bep\b construc")

# Inspeccion fiscal / tecnica de obras: NUNCA se protege ni se incluye (salvo Nivel A).
INSPECCION = C(r"inspeccion fiscal|\baif\b|\baifo\b|asesoria a la inspecc|inspeccion tecnica|\bito\b")

# 2) EXCLUIR: obras de infraestructura + inspeccion fiscal de obras + insumos.
#    OJO: tokens con \b para no hacer match dentro de palabras legitimas
#    (p.ej. "racion" dentro de "generacion/elaboracion", "ropa" en "Europa",
#     "aseo" en "paseo", "banos" en "urbanos").
EXCLUIR = C(r"inspeccion fiscal|\baif\b|\baifo\b|asesoria a la inspecc|inspeccion tecnica|\bito\b|"
            r"\bobra(s)?\b|construccion|conservacion|mantencion|reposicion|repos\.|pavimenta|asfalt|"
            r"alcantarilla|colector de agua|saneamiento|agua potable|alcantarillado|puente(?!.*estudio)|"
            r"suministro|adquisicion|\badq\b|\badq\.|arriendo|compra de|provision de|"
            r"senaletic|demarcacion|semaforizacion|instalacion de semaf|iluminacion|alumbrado|luminaria|"
            r"edificacion|edificio|remodelacion|\bbanos?\b|climatizacion|ascensor|areas verdes|"
            r"neumatic|naumatic|combustible|petroleo|lubricante|repuestos|pijama|\bropa\b|vestuario|"
            r"transporte escolar|transporte de (residuos|aridos|agua|personal|pasajeros|carga|alimentos|lena|valores|internos|funcionarios?|mezcla|material|hormigon)|"
            r"servicio de transporte|\baseo\b|vigilancia|guardias|alimentacion|\braciones?\b|destruccion de|mercancias")

# 3) ON_TEMA: transporte + planificacion urbana/territorial.
TEMA = C(r"transporte|movilidad|\bvial\b|\bvialidad\b|\btransito\b|\btrafico\b|peaton|ciclo|"
         r"\burban|territorial|plan regulador|\bpladeco\b|uso de suelo|suelo urbano|mercado de suelo|espacio publico|\bpiep\b|"
         r"origen.?destino|demanda de viaje|particion modal|accesibilidad|logistic|portuari|concesion|"
         r"\brutas?\b|\bcaminos?\b|corredor|pasada urbana|conectividad")

# Organismos clave — se evalua sobre organismo + unidad.
# NIVEL A: agencias de planificacion de transporte/territorio -> entra TODO
#          lo que licitan (no hacen obras; sus insumos como ortofotos son
#          parte de estudios). Se salta el filtro de obra.
ORG_A = C(r"sectra|programa de vialidad y transporte urbano|secretariatransporte|"
          r"secretaria\s*de?\s*planificacion.*transporte|"
          r"transporte publico regional|\bdtpr\b|transporte publico metropolitano|\bdtpm\b|directorio de transporte|"
          r"\bdirplan\b|direccion de planeamiento")
# NIVEL B: organismos que hacen obras y estudios -> solo sus ESTUDIOS, con estrella.
ORG_B = C(r"direccion de vialidad|\bvialidad\b|\bconcesiones\b|direccion general de concesiones|"
          r"\bserviu\b|servicio de vivienda y urbanizacion|vivienda y urbanismo|\bminvu\b|seremi.*vivienda")
MUNI = C(r"municipalidad|\bmuni\b|i\.? municipalidad")
PIEP = C(r"\bpiep\b|plan de inversion(es)? en (infraestructura|movilidad|espacio)|"
         r"inversiones en espacio publico|aporte.*espacio publico|infraestructura de movilidad y espacio publico")

# Cache de prefijos de organismos clave (data/key_orgs.json). Se siembra con
# los conocidos y se auto-completa: cualquier licitacion cuyo prefijo este aqui
# se consulta en detalle aunque el nombre no calce con el tema.
KEY_ORGS_SEED = {"520663": "SECTRA (Gran Concepcion)", "619284": "SECTRA (Talca-Maule)"}

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
        if re.search(pat, t, re.I):
            puntaje += peso
            cats.append(cat)
    return puntaje, cats

def fmt_monto(det):
    m = det.get("MontoEstimado"); mon = det.get("Moneda") or ""
    if not m: return ""
    try: return f"{float(m):,.0f} {mon}".replace(",", ".")
    except Exception: return f"{m} {mon}"

def main():
    modo = "TICKET DE PRUEBA (limitado)" if ES_TEST else "ticket personal"
    print(f"Radar Mercado Publico — {modo}")
    data = get(f"{BASE}?estado=activas&ticket={TICKET}")
    if not data or "Listado" not in data:
        sys.exit("No se pudo descargar el listado de licitaciones activas.")
    listado = data["Listado"]
    print(f"  {len(listado)} activas.")

    # Cache de prefijos de organismos clave (se siembra y se auto-completa).
    kpath = os.path.join(DATA, "key_orgs.json")
    key_orgs = dict(KEY_ORGS_SEED)
    if os.path.exists(kpath):
        try: key_orgs.update(json.load(open(kpath, encoding="utf-8")))
        except Exception: pass

    def prefijo(cod): return cod.split("-")[0]

    # Primer paso: se consulta el detalle de lo que parece estudio/tema por su
    # nombre, MAS todo lo de organismos clave conocidos (por prefijo), aunque el
    # nombre no calce (asi no se pierde, p.ej., una ortofoto de SECTRA).
    candidatas = []
    # códigos MOP de estudio al inicio del nombre: EI (Estudio de Ingeniería),
    # EP (Estudio de Preinversión), EII, e.i., e.p.
    tipo_mop = re.compile(r"^(ei|eii|ep|e\.i|e\.p)\b")
    for lic in listado:
        n = sin_tildes(lic.get("Nombre", ""))
        es_key = prefijo(lic["CodigoExterno"]) in key_orgs
        if not (es_key or tipo_mop.match(n) or ESTUDIO.search(n) or ESTUDIO_FUERTE.search(n) or TEMA.search(n) or PIEP.search(n)):
            continue
        p = clasificar(lic.get("Nombre", ""))[0]
        p += 5 if es_key else (3 if ESTUDIO.search(n) else (2 if tipo_mop.match(n) else 0))
        candidatas.append({**lic, "p": p, "es_key": es_key})
    candidatas.sort(key=lambda x: -x["p"])
    print(f"  {len(candidatas)} candidatas (incl. organismos clave sembrados).")
    if len(candidatas) > MAX_DETALLE:
        print(f"  (limito el detalle a {MAX_DETALLE})")
        candidatas = candidatas[:MAX_DETALLE]

    resultados = []
    for i, c in enumerate(candidatas):
        cod = c["CodigoExterno"]
        d = get(f"{BASE}?codigo={cod}&ticket={TICKET}")
        time.sleep(THROTTLE)
        det = (d or {}).get("Listado", [{}])[0] if d else {}
        desc = det.get("Descripcion", "") or ""
        comp = det.get("Comprador") or {}
        organismo = comp.get("NombreOrganismo", "")
        unidad = comp.get("NombreUnidad", "")

        texto = sin_tildes(c["Nombre"] + " " + desc)
        org = sin_tildes(organismo + " " + unidad)

        es_estudio = bool(ESTUDIO.search(texto))
        # Bloqueado = inspeccion fiscal (nunca se protege), o palabra de obra/insumo
        # SIN un marcador fuerte de estudio (preinversion/plan/imiv...) que lo rescate.
        es_obra    = bool(INSPECCION.search(texto) or
                          (EXCLUIR.search(texto) and not ESTUDIO_FUERTE.search(texto)))
        on_tema    = bool(TEMA.search(texto))
        org_a      = bool(ORG_A.search(org))
        org_b      = bool(ORG_B.search(org))
        muni_piep  = bool(MUNI.search(org) and PIEP.search(texto))

        # Auto-aprende SOLO prefijos de Nivel A (agencias de planificacion, pocas
        # y todas relevantes). Nivel B se capta por nombre, no por prefijo, para
        # no traer a detalle cientos de obras de Vialidad/SERVIU.
        if org_a and prefijo(cod) not in key_orgs:
            key_orgs[prefijo(cod)] = (unidad or organismo)[:60]

        p2, cats2 = clasificar(c["Nombre"] + " " + desc)

        # Regla final por niveles:
        #  A) agencia de planificacion  -> entra TODO (se salta filtro de obra).
        #  B/muni/general -> solo estudios, no obra, y del tema (o org B) con >=1 pto.
        if org_a:
            star = True
        elif es_estudio and not es_obra and (org_b or muni_piep or (on_tema and p2 >= 1)):
            star = org_b or muni_piep
        else:
            razon = "obra/no-estudio" if (not es_estudio or es_obra) else f"fuera de tema (p={p2})"
            print(f"  [-] {cod} {razon}")
            continue

        if star: p2 += 4
        if muni_piep or PIEP.search(texto): p2 += 3
        fch = det.get("Fechas") or {}
        print(f"  [+] {p2:>2} {cod} {'*' if star else ' '} {c['Nombre'][:50]}")
        resultados.append({
            "codigo": cod,
            "nombre": c["Nombre"],
            "puntaje": p2,
            "categorias": sorted(set(cats2)),
            "org_clave": star,
            "bip": det.get("CodigoBIP") or "",
            "organismo": organismo,
            "unidad": unidad,
            "region": comp.get("RegionUnidad", ""),
            "tipo": det.get("Tipo", ""),
            "monto": fmt_monto(det),
            "fecha_cierre": (fch.get("FechaCierre") or c.get("FechaCierre") or "")[:16],
            "fecha_publicacion": (fch.get("FechaPublicacion") or "")[:10],
            "descripcion": desc[:900],
            "url": f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={cod}",
        })

    resultados.sort(key=lambda x: (-x["puntaje"], x["fecha_cierre"] or "9"))

    with open(kpath, "w", encoding="utf-8") as f:
        json.dump(key_orgs, f, ensure_ascii=False, indent=1, sort_keys=True)

    with open(os.path.join(DATA, "resultados.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)
    if resultados:
        cols = ["codigo", "nombre", "puntaje", "org_clave", "organismo", "region",
                "monto", "fecha_cierre", "fecha_publicacion", "url"]
        with open(os.path.join(DATA, "resultados.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(resultados)

    meta = {
        "actualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "total_activas": len(listado),
        "candidatas": len(candidatas),
        "resultados": len(resultados),
        "clave": sum(1 for r in resultados if r["org_clave"]),
        "modo_ticket": "prueba" if ES_TEST else "personal",
        "regiones": sorted({r["region"] for r in resultados if r["region"]}),
        "categorias": list(CATEGORIAS.keys()),
    }
    with open(os.path.join(DATA, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"Listo: {len(resultados)} estudios ({meta['clave']} de organismos clave).")

if __name__ == "__main__":
    main()
