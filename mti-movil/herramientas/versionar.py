"""Sube la versión de la app en los cuatro sitios donde tiene que coincidir.

Sin esto la actualización llega a medias: el navegador se trae el `index.html`
nuevo pero reutiliza de su caché HTTP el `app.js` viejo, y la app queda con
pantallas que existen y funciones que no. Pasó, y cuesta un rato de diagnóstico.

La versión aparece en:

  sw.js        VERSION, que nombra las cachés del service worker
  index.html   las consultas ?v= de styles.css y app.js
  app.js       la consulta ?v= al crear el worker
  sw.js        RECURSOS, que precachea esas mismas URL con su consulta

Uso, desde la carpeta de la app:

    python3 herramientas/versionar.py 6
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ARCHIVOS_VERSIONADOS = ("styles.css", "app.js", "worker.js")


def _sustituir(texto: str, patron: str, reemplazo: str, ruta: Path) -> str:
    nuevo, cuenta = re.subn(patron, reemplazo, texto)
    if not cuenta:
        raise SystemExit(f"No se encontró «{patron}» en {ruta.name}; revisa el archivo a mano")
    return nuevo


def versionar(raiz: Path, version: int) -> None:
    sw = raiz / "sw.js"
    texto = sw.read_text(encoding="utf-8")
    texto = _sustituir(texto, r'const VERSION = "mti-movil-v\d+";',
                       f'const VERSION = "mti-movil-v{version}";', sw)
    for nombre in ARCHIVOS_VERSIONADOS:
        texto = _sustituir(texto, rf'"{re.escape(nombre)}(\?v=\d+)?"',
                           f'"{nombre}?v={version}"', sw)
    sw.write_text(texto, encoding="utf-8")

    html = raiz / "index.html"
    texto = html.read_text(encoding="utf-8")
    for nombre in ("styles.css", "app.js"):
        texto = _sustituir(texto, rf'{re.escape(nombre)}(\?v=\d+)?"',
                           f'{nombre}?v={version}"', html)
    html.write_text(texto, encoding="utf-8")

    app = raiz / "app.js"
    texto = app.read_text(encoding="utf-8")
    texto = _sustituir(texto, r'new Worker\("worker\.js(\?v=\d+)?"',
                       f'new Worker("worker.js?v={version}"', app)
    app.write_text(texto, encoding="utf-8")

    print(f"  versión v{version} aplicada en sw.js, index.html y app.js")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", type=int, help="número de versión, p. ej. 6")
    parser.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    if args.version < 1:
        parser.error("la versión debe ser un entero positivo")
    versionar(args.raiz, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
