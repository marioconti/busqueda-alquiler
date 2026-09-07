"""Servidor local minimo. Elimina el paso manual de mover decisiones.json a mano.

QUE RESUELVE
------------
Con la pagina abierta por doble click (file://), el navegador no puede escribir en el
disco: por eso la version anterior descargaba un decisiones.json que vos tenias que
mover a web/pendiente.json. Un paso manual en CADA iteracion.

Sirviendo la misma pagina desde localhost, el boton "Descartar" escribe directo en
data/eventos.jsonl y se acabo el paso manual.

NO ES UN SERVICIO. Es un proceso que abris cuando queres mirar la pagina y cerras
cuando terminas, igual que abrias el archivo. Se levanta con abrir.bat (doble click).
Biblioteca estandar, cero dependencias.

SEGURIDAD: escucha SOLO en 127.0.0.1. No es alcanzable desde la red.

La pagina sigue funcionando con doble click en web/index.html; en ese modo vuelve sola
al mecanismo de localStorage + exportar. Detecta cual de los dos tiene disponible.
"""

from __future__ import annotations

import json
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build  # noqa: E402
import eventos  # noqa: E402
from lib_config import DIR_WEB  # noqa: E402

PUERTO = 8787
_candado = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def _json(self, codigo: int, cuerpo: dict) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/api/evento":
            return self._json(404, {"error": "ruta desconocida"})
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 1_000_000:
                return self._json(413, {"error": "cuerpo demasiado grande"})
            ev = json.loads(self.rfile.read(largo).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            return self._json(400, {"error": f"json invalido: {e}"})

        tipo = ev.pop("tipo", None)
        if tipo not in eventos.TIPOS:
            return self._json(400, {"error": f"tipo invalido: {tipo}"})
        # El motivo del descarte es OPCIONAL desde el 2026-08-24 (Mario: "a veces no
        # tengo ganas de poner la razon"). No se rechaza el pedido: se etiqueta, para
        # que un descarte mudo siga siendo contable en descartados_por_motivo en vez de
        # caer en el mismo balde que "escribio texto pero no eligio chip".
        if tipo == "descarte" and not (ev.get("motivo") or "").strip():
            ev.pop("motivo", None)
            ev.setdefault("categoria", "sin_motivo")

        with _candado:   # un solo escritor por vez: la bitacora no se pisa
            guardado = eventos.registrar(tipo, ev.pop("id", None), origen="web", **ev)
            eventos.sincronizar()
            resumen = build.build()
        self._json(200, {"ok": True, "evento": guardado, "resumen": resumen})

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/api/eventos":
            return self._json(200, {"eventos": eventos.leer()[-200:]})
        super().do_GET()

    def end_headers(self) -> None:
        # data.js se regenera en cada decision: si el navegador lo cachea, la pagina
        # muestra el estado anterior y parece que el boton no hizo nada.
        if self.path.endswith((".js", ".json", ".css", ".html")) or self.path.endswith("/"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, formato, *args):  # silencio: solo interesan los errores
        if not str(args[0] if args else "").startswith(("GET /fotos", "GET /data.js")):
            sys.stderr.write("  %s\n" % (formato % args))


def correr(puerto: int = PUERTO, abrir: bool = True) -> None:
    build.build()  # que lo primero que se vea este al dia
    handler = partial(Handler, directory=str(DIR_WEB))
    with ThreadingHTTPServer(("127.0.0.1", puerto), handler) as srv:
        url = f"http://127.0.0.1:{puerto}/index.html"
        print(f"Busqueda de alquiler -> {url}")
        print("Las decisiones se guardan solas en data/eventos.jsonl")
        print("Ctrl+C para cerrar.\n")
        if abrir:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nCerrado.")


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else PUERTO
    correr(p, abrir="--sin-abrir" not in sys.argv)
