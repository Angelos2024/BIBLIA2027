# -*- coding: utf-8 -*-
"""Sirve el visor de solo lectura en http://127.0.0.1:8090/"""
import http.server
import socketserver
from pathlib import Path

PORT = 8090  # distinto de 7081 (editor local con escritura)
ROOT = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        self.send_error(405, "Solo lectura: no hay API de edición")


class Servidor(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    with Servidor(("", PORT), Handler) as httpd:
        print(f"Visor solo lectura → http://127.0.0.1:{PORT}/")
        print("  (Génesis 1–28 · sin ediciones)")
        httpd.serve_forever()
