"""Extrae la cuadrícula comparativa de las nueve lecturas.

El informe de escritorio `similitudes-corpus-nueve-lecturas.html` lleva sus datos
incrustados en `window.__OB__`: nueve matrices de 25×25, el puesto de cada par
dentro de los trescientos, los empates y los sectores de cada obra.

Este guion los saca de ahí y los deja en un JSON que la app dibuja. No recalcula
nada: son exactamente las mismas cifras del informe.

Uso:

    python3 herramientas/generar_nueve_lecturas.py \
        --html "ruta/al/similitudes-corpus-nueve-lecturas.html" \
        --salida corpus
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# Orden y nombre de cada lectura, tal como los rotula el informe original.
LECTURAS = [
    ("musicologico", "Musicológico ponderado", "distancia ponderada por rasgos"),
    ("mti_mel", "MTI melódico", "perfil MTI sobre la línea melódica"),
    ("mti_arm", "MTI armónico", "perfil MTI sobre la textura armónica"),
    ("sust_mel", "Sustitución melódica", "coste de sustitución, melódico"),
    ("sust_arm", "Sustitución armónica", "coste de sustitución, armónico"),
    ("phi", "Rasgos φ(G)", "descriptores derivados del grafo"),
    ("phi_arm", "Rasgos φ(G) armonizado", "los mismos, sobre la armonía"),
    ("contable", "Rasgos contables", "recuentos estructurales"),
    ("edicion", "Edición manual", "distancia de edición anotada a mano"),
]


def _bloque_json(texto: str, marcador: str) -> Any:
    """Recorta el objeto que sigue a un marcador, emparejando llaves."""

    encaje = re.search(rf"{re.escape(marcador)}\s*=\s*\{{", texto)
    if not encaje:
        raise SystemExit(f"No encuentro «{marcador}» en el HTML")
    inicio = encaje.end() - 1
    profundidad = 0
    for indice in range(inicio, len(texto)):
        if texto[indice] == "{":
            profundidad += 1
        elif texto[indice] == "}":
            profundidad -= 1
            if profundidad == 0:
                return json.loads(texto[inicio : indice + 1])
    raise SystemExit(f"El objeto de «{marcador}» está truncado")


def generar(html: Path, salida: Path) -> None:
    datos = _bloque_json(html.read_text(encoding="utf-8", errors="replace"), "window.__OB__")

    obras = datos["nom"]
    sectores = datos["sec"]
    total = len(obras)

    # Los sectores llegan por obra; para filtrar pares hace falta el conjunto.
    catalogo: dict[str, int] = {}
    for lista in sectores:
        for sector in lista:
            catalogo[sector] = catalogo.get(sector, 0) + 1

    lecturas = []
    for clave, nombre, descripcion in LECTURAS:
        matriz = datos["M"].get(clave)
        if not matriz:
            continue
        lecturas.append(
            {
                "id": clave,
                "nombre": nombre,
                "descripcion": descripcion,
                "matriz": [[round(v, 6) for v in fila] for fila in matriz],
                "puestos": datos["pos"].get(clave),
                "empates": datos["emp"].get(clave),
                "global": datos["glob"].get(clave),
            }
        )

    paquete = {
        "fuente": "similitudes-corpus-nueve-lecturas",
        "obras": obras,
        "sectores": sectores,
        "catalogo": dict(sorted(catalogo.items(), key=lambda x: (-x[1], x[0]))),
        "pares": total * (total - 1) // 2,
        "lecturas": lecturas,
    }

    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / "nueve-lecturas.json"
    destino.write_text(
        json.dumps(paquete, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  nueve-lecturas.json   {destino.stat().st_size / 1024:7.1f} KB")
    print(f"  {total} obras · {paquete['pares']} pares · {len(lecturas)} lecturas "
          f"· {len(catalogo)} sectores")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    if not args.html.is_file():
        parser.error(f"No existe {args.html}")
    generar(args.html.resolve(), args.salida.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
