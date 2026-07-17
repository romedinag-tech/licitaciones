# -*- coding: utf-8 -*-
"""
Panel Radar — servidor local que orquesta todo el flujo con un clic:
descargar antecedentes → analizar bases → abrir el analizador.

Sirve 'panel.html' (con el radar embebido y los botones) y ejecuta los
scripts al pulsar cada botón, mostrando el avance en vivo.

Arráncalo con doble clic en 'Panel Radar.bat'. Se abre solo en el navegador.
No cierres la ventana negra mientras lo uses.
"""
import http.server, socketserver, threading, subprocess, sys, os, json, webbrowser, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = pathlib.Path(__file__).parent
PORT = 8799
DESTINO = pathlib.Path(os.environ.get(
    "RADAR_DESTINO", pathlib.Path.home() / "Análisis RMG" / "Licitaciones"))

estado = {"running": None, "log": []}
lock = threading.Lock()

def _log(msg):
    with lock:
        estado["log"].append(msg)

def run_script(nombre, args, tarea, abrir_al_final=False):
    with lock:
        estado["running"] = tarea
        estado["log"] = [f"▶ {tarea}…"]
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(AQUI / nombre), *args],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", cwd=str(AQUI), env=env)
        for line in proc.stdout:
            _log(line.rstrip("\n"))
        proc.wait()
        _log(f"✔ Listo — {tarea}." if proc.returncode == 0 else f"✗ Terminó con error ({tarea}).")
        if abrir_al_final and proc.returncode == 0:
            abrir_analizador()
    except Exception as e:
        _log(f"✗ Error: {e}")
    finally:
        with lock:
            estado["running"] = None

def tarea_todo():
    run_script("descargar_antecedentes.py", [], "Descargar antecedentes")
    if estado["log"] and not estado["log"][-1].startswith("✗"):
        run_script("analizar_bases.py", ["--no-abrir"], "Analizar bases", abrir_al_final=True)

def abrir_analizador():
    f = DESTINO / "Analizador de Bases.html"
    try:
        if f.exists():
            os.startfile(str(f)); _log("↗ Analizador abierto.")
        else:
            _log("(aún no existe el analizador; corre 'Analizar bases' primero.)")
    except Exception as e:
        _log(f"No se pudo abrir: {e}")

def lanzar(fn, *a):
    if estado["running"]:
        return False
    threading.Thread(target=fn, args=a, daemon=True).start()
    return True

class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a):
        pass
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (AQUI / "panel.html").read_text(encoding="utf-8"),
                       "text/html; charset=utf-8")
        elif self.path == "/status":
            with lock:
                self._send(200, json.dumps(estado, ensure_ascii=False))
        else:
            self._send(404, "{}")
    def do_POST(self):
        rutas = {
            "/run/todo":       lambda: lanzar(tarea_todo),
            "/run/descargar":  lambda: lanzar(run_script, "descargar_antecedentes.py", [], "Descargar antecedentes"),
            "/run/analizar":   lambda: lanzar(run_script, "analizar_bases.py", ["--no-abrir"], "Analizar bases", True),
            "/abrir":          lambda: lanzar(abrir_analizador),
        }
        fn = rutas.get(self.path)
        if not fn:
            self._send(404, "{}"); return
        if estado["running"]:
            self._send(409, json.dumps({"error": f"En curso: {estado['running']}"})); return
        fn()
        self._send(200, json.dumps({"ok": True}))

def main():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/"
        print(f"Panel Radar corriendo en {url}")
        print("Se abrirá en tu navegador. NO cierres esta ventana mientras lo uses.")
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
