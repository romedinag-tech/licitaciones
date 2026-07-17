# -*- coding: utf-8 -*-
"""
Analizador de bases de licitaciones — Medina Consultoría SpA.

Corre LOCAL. Lee las bases que descargaste (PDF/DOCX/ZIP) en la carpeta
de licitaciones, extrae su texto, detecta la estructura de secciones y
clasifica los "puntos clave" (plazos, garantías, presupuesto, criterios de
evaluación, tareas/alcance, entregables, multas, equipo). Genera:

  - bases_data.js         (los datos, para el visor)
  - Analizador de Bases.html   (copia del visor)

Ambos en la carpeta de licitaciones. Abre el HTML para leer, recorrer con
índice hipervinculado y destacar tareas (se guardan en tu navegador).

Requisitos:  pip install pymupdf python-docx
"""
import sys, os, re, json, zipfile, pathlib, datetime, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = pathlib.Path(os.environ.get(
    "RADAR_DESTINO", pathlib.Path.home() / "Análisis RMG" / "Licitaciones"))
AQUI = pathlib.Path(__file__).parent

# --- OCR (Tesseract vía PyMuPDF) para PDFs escaneados ---
def _find_tessdata():
    for p in [os.environ.get("TESSDATA_PREFIX"),
              r"C:\Program Files\Tesseract-OCR\tessdata",
              r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
              str(pathlib.Path.home() / "AppData/Local/Programs/Tesseract-OCR/tessdata")]:
        if p and os.path.isdir(p):
            return p
    return None
TESSDATA = _find_tessdata()
if TESSDATA:
    os.environ["TESSDATA_PREFIX"] = TESSDATA
OCR_OK = TESSDATA is not None

# --- clasificación del tipo de documento por nombre de archivo ---
def tipo_doc(nombre):
    n = sin_tildes(nombre).lower()
    if "administrativ" in n: return ("Administrativa", "adm")
    if re.search(r"\bbt[_ ]|tecnic|terminos.*referenc|\btdr\b|especificac", n): return ("Técnica", "tec")
    if "anexo" in n: return ("Anexos", "anx")
    if "presupuesto" in n: return ("Presupuesto", "eco")
    if re.search(r"decreto|resoluc|aprueba|\bres\b", n): return ("Resolución", "res")
    if "concurso" in n or "bases" in n: return ("Bases", "bas")
    return ("Documento", "doc")

# --- categorías de puntos clave (se buscan en los títulos de sección) ---
CATEGORIAS = [
    ("Plazos y fechas",        r"plazo|calendario|cronograma|vigencia|fecha"),
    ("Garantías",              r"garantia|boleta|fiel cumplimiento|seriedad"),
    ("Presupuesto y pagos",    r"presupuesto|monto|precio|\bpago|estados de pago|financiamiento|reajuste"),
    ("Criterios de evaluación",r"evaluacion|pauta|ponderaci|puntaje|criterio"),
    ("Requisitos y oferentes", r"requisito|participante|admisibilidad|oferente|union temporal|\butp\b"),
    ("Tareas y alcance (TDR)", r"tarea|alcance|objetivo|actividad|metodolog|desarrollo de proyecto|estudios de base|considerac"),
    ("Entregables e informes", r"informe|entrega|producto|avance|recepcion|exposici"),
    ("Multas y término",       r"multa|sancion|termino anticipado|incumplimiento|caducidad"),
    ("Equipo de trabajo",      r"equipo|profesional|personal clave|recurso humano"),
]
STOP_TITULOS = re.compile(r"^(puntos?|republica de chile|pagina)\b", re.I)

def sin_tildes(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()

def limpia_titulo(t):
    return re.sub(r"\s+", " ", t).strip(" .:-")

def es_titulo(t):
    """Heurística: título de sección = mayúsculas, con sustancia."""
    t = t.strip()
    if len(t) < 6 or len(t) > 85: return False
    if STOP_TITULOS.search(t): return False
    letras = [c for c in t if c.isalpha()]
    if not letras: return False
    up = sum(1 for c in letras if c.isupper())
    return up >= len(letras) * 0.7            # >=70% mayúsculas

def secciones_de_texto(txt):
    """Detecta secciones numeradas; devuelve [(num, titulo, cuerpo)]."""
    # posiciones de encabezados: número + título en MAYÚSCULAS (puede cruzar \n)
    pat = re.compile(r"(?m)^\s*(\d{1,2}(?:\.\d{1,2}){0,2})[\.\)]?\s+"
                     r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,.\-()/°ª\"']{3,84})")
    cands = []
    for m in pat.finditer(txt):
        titulo = limpia_titulo(m.group(2))
        if es_titulo(titulo):
            cands.append((m.start(), m.group(1), titulo))
    # descarta títulos que se repiten mucho (encabezados/pies de página)
    from collections import Counter
    frec = Counter(t for _, _, t in cands)
    cands = [c for c in cands if frec[c[2]] <= 4]
    # arma secciones con el cuerpo entre encabezados
    secs = []
    for i, (pos, num, tit) in enumerate(cands):
        fin = cands[i + 1][0] if i + 1 < len(cands) else len(txt)
        cuerpo = re.sub(r"\n{3,}", "\n\n", txt[pos:fin]).strip()
        secs.append({"num": num, "titulo": tit, "texto": cuerpo})
    return secs

def leer_pdf(path):
    import fitz
    doc = fitz.open(path)
    paginas = [pg.get_text() for pg in doc]
    doc.close()
    return "".join(paginas), paginas

def ocr_pdf(path):
    """OCR página a página (español) para PDFs escaneados."""
    import fitz
    doc = fitz.open(path); paginas = []
    n = doc.page_count
    for i, pg in enumerate(doc):
        try:
            tp = pg.get_textpage_ocr(language="spa", dpi=200, full=True)
            paginas.append(pg.get_text(textpage=tp))
        except Exception:
            paginas.append("")
        print(f"       OCR página {i + 1}/{n}", end="\r")
    doc.close(); print()
    return "".join(paginas), paginas

def leer_docx(path):
    import docx
    d = docx.Document(str(path))
    partes = [p.text for p in d.paragraphs]
    for tbl in d.tables:                       # los anexos suelen ser tablas
        for row in tbl.rows:
            partes.append(" | ".join(c.text for c in row.cells))
    return "\n".join(partes), None

def procesar_documento(path):
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            txt, paginas = leer_pdf(path)
        elif ext == ".docx":
            txt, paginas = leer_docx(path)
        else:
            return None
    except Exception as e:
        print(f"     no se pudo leer {path.name}: {str(e)[:60]}")
        return None
    nombre, cls = tipo_doc(path.name)
    ocr_usado = False
    if len((txt or "").strip()) < 200 and ext == ".pdf" and OCR_OK:
        print(f"     {path.name[:40]}: escaneado -> OCR en español…")
        try:
            txt, paginas = ocr_pdf(path); ocr_usado = True
        except Exception as e:
            print(f"     OCR falló: {str(e)[:50]}")
    if len((txt or "").strip()) < 200:         # sigue sin texto legible
        nota = ("Sin capa de texto y OCR no disponible (instala Tesseract)."
                if not OCR_OK else "No se pudo extraer texto ni con OCR.")
        return {"archivo": path.name, "tipo": nombre, "cls": cls,
                "paginas": len(paginas) if paginas else None,
                "escaneado": True, "secciones": [], "claves": {}, "nota": nota}
    secs = secciones_de_texto(txt)
    if len(secs) < 3 and paginas:      # sin estructura clara -> por página
        secs = [{"num": str(i + 1), "titulo": f"Página {i + 1}",
                 "texto": re.sub(r"\n{3,}", "\n\n", p).strip()}
                for i, p in enumerate(paginas) if p.strip()]
    if not secs:                        # con texto pero sin secciones ni páginas (docx)
        secs = [{"num": "", "titulo": "Contenido",
                 "texto": re.sub(r"\n{3,}", "\n\n", txt).strip()}]
    # clasifica secciones en categorías de puntos clave
    claves = {}
    for idx, s in enumerate(secs):
        low = sin_tildes(s["titulo"]).lower()
        for cat, pat in CATEGORIAS:
            if re.search(pat, low):
                snip = re.sub(r"\s+", " ", s["texto"])[:220]
                claves.setdefault(cat, []).append(
                    {"i": idx, "titulo": f'{s["num"]} {s["titulo"]}', "snippet": snip})
    return {"archivo": path.name, "tipo": nombre, "cls": cls,
            "paginas": len(paginas) if paginas else None, "ocr": ocr_usado,
            "secciones": secs, "claves": claves}

def main():
    if not BASE_DIR.exists():
        sys.exit(f"No existe la carpeta {BASE_DIR}")
    print(f"Carpeta: {BASE_DIR}\n")
    licitaciones = []
    for carpeta in sorted([d for d in BASE_DIR.iterdir() if d.is_dir()]):
        # descomprime ZIPs si hay
        for z in carpeta.glob("*.zip"):
            try:
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(carpeta / (z.stem + "_extraido"))
                print(f"  [zip] {z.name} descomprimido")
            except Exception as e:
                print(f"  [zip] error {z.name}: {e}")
        docs = []
        vistos = set()
        for f in sorted(carpeta.rglob("*")):
            if f.suffix.lower() in (".pdf", ".docx") and f.is_file():
                clave = f.stat().st_size            # dedup copias "(1)" idénticas
                if clave in vistos:
                    print(f"  (dup) se omite {f.name}"); continue
                vistos.add(clave)
                d = procesar_documento(f)
                if d:
                    docs.append(d)
                    nsec = len(d["secciones"]); nclv = sum(len(v) for v in d["claves"].values())
                    print(f"  {carpeta.name} / {f.name[:45]}  [{d['tipo']}] {nsec} secc, {nclv} claves")
        if docs:
            licitaciones.append({"carpeta": carpeta.name,
                                 "titulo": re.sub(r"^\d+\s*", "", carpeta.name),
                                 "documentos": docs})

    data = {"generado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "licitaciones": licitaciones}
    salida_js = BASE_DIR / "bases_data.js"
    with open(salida_js, "w", encoding="utf-8") as fp:
        fp.write("window.BASES = ")
        json.dump(data, fp, ensure_ascii=False)
        fp.write(";")
    # copia el visor
    visor = AQUI / "analizador_bases.html"
    destino = None
    if visor.exists():
        destino = BASE_DIR / "Analizador de Bases.html"
        destino.write_text(visor.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\nVisor copiado a: {destino}")
    tot_doc = sum(len(l["documentos"]) for l in licitaciones)
    print(f"\nListo: {len(licitaciones)} licitaciones, {tot_doc} documentos.")
    print(f"Datos: {salida_js}")
    if destino and "--no-abrir" not in sys.argv:
        try:
            os.startfile(str(destino))          # abre el visor (Windows)
        except Exception:
            print("Abre 'Analizador de Bases.html' en la carpeta de licitaciones.")

if __name__ == "__main__":
    main()
