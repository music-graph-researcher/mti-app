"""Genera el informe del corpus extendido (8005) que la app muestra.

Por cada textura calcula sus lecturas comparativas —estructural, rítmica y las
contextuales por componente del §3.6— y de cada una obtiene su matriz de
disimilitud, su clustering, su silueta, su homología persistente y su medoide.
Nueve lecturas en armónica; ocho en melódica, que no tiene movimiento del bajo.

Como el resto del corpus, esto se calcula aquí una vez (7 s) y la app solo lo
presenta. Las matrices exactas se descartan: ocupan el triple y la interfaz solo
las usa para pintar. Los valores exactos siguen donde importan, en cada
comparación que la app calcula en vivo.

Uso, desde la raíz del proyecto MTI:

    python3 ruta/a/mti-movil/herramientas/generar_extendido.py \
        --proyecto . --salida ruta/a/mti-movil/corpus
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any


def _valor(celda: Any) -> float | None:
    if isinstance(celda, dict):
        return celda.get("value")
    return celda


def _matriz(matriz: Any) -> list[list[float | None]]:
    return [[_valor(c) for c in fila] for fila in (matriz or [])]


def _pureza(familias: list[dict[str, Any]], etiquetas: dict[str, str]) -> float | None:
    """Media de la pureza de cada familia respecto de la etiqueta publicitaria.

    La etiqueta no interviene en ninguna distancia: se mide después, para
    preguntar si la estructura reproduce el reparto por sectores.
    """

    valores = []
    for familia in familias:
        cuenta = collections.Counter(
            etiquetas.get(miembro) for miembro in familia.get("members", [])
        )
        if cuenta:
            valores.append(max(cuenta.values()) / sum(cuenta.values()))
    return sum(valores) / len(valores) if valores else None


def _rasgos(persistencia: Any, grado: str) -> int:
    bloque = (persistencia or {}).get(grado)
    if isinstance(bloque, dict):
        return len(bloque.get("features", []))
    return len(bloque or [])


def _lectura(cruda: dict[str, Any], etiquetas: dict[str, str], medoides: dict[str, Any]) -> dict[str, Any]:
    familias = cruda.get("families") or []
    medoide = medoides.get(cruda["id"]) or {}
    return {
        "id": cruda["id"],
        "tipo": cruda.get("kind"),
        "silueta": cruda.get("silhouette"),
        "familias": [
            {"id": f.get("id"), "miembros": f.get("members", [])} for f in familias
        ],
        "pureza": _pureza(familias, etiquetas),
        "H0": _rasgos(cruda.get("persistence"), "H0"),
        "H1": _rasgos(cruda.get("persistence"), "H1"),
        "medoide": {"id": medoide.get("medoid"), "obra": medoide.get("work"),
                    "compositor": medoide.get("composer")},
        "matriz": _matriz(cruda.get("distance_matrix")),
    }


def generar(proyecto: Path, salida: Path) -> None:
    sys.path.insert(0, str(proyecto))
    from backend.corpus_extended import analyze_extended_corpus, load_corpus_records

    registros = load_corpus_records(proyecto / "nice-dataset-main")

    grupos: dict[str, list[dict[str, Any]]] = {}
    for registro in registros:
        grupos.setdefault(str(registro.get("texture") or "sin_textura"), []).append(registro)

    texturas = []
    for textura, grupo in sorted(grupos.items()):
        crudo = analyze_extended_corpus(grupo, modes=("structural", "rhythm", "contextual"))
        etiquetas = (crudo.get("advertising") or {}).get("single", {})
        medoides = crudo.get("kitsch") or {}
        texturas.append(
            {
                "textura": textura,
                "registros": len(grupo),
                "ids": [r["id"] for r in grupo],
                "obras": {r["id"]: (r.get("metadata") or {}).get("work") for r in grupo},
                "sectores": etiquetas,
                "lecturas": [_lectura(l, etiquetas, medoides) for l in crudo.get("readings", [])],
            }
        )

    informe = {
        "protocolo": "MOTIF2-extended-corpus-1.0",
        "corpus": {
            "registros": len(registros),
            "texturas": [t["textura"] for t in texturas],
        },
        "texturas": texturas,
    }

    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / "extendido.json"
    destino.write_text(
        json.dumps(informe, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  extendido.json   {destino.stat().st_size / 1024:7.1f} KB")
    for t in texturas:
        print(f"  {t['textura']:<12} {t['registros']:>3} registros · {len(t['lecturas'])} lecturas")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proyecto", type=Path, default=Path("."))
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()

    if not (args.proyecto / "backend" / "corpus_extended.py").is_file():
        parser.error(f"No encuentro backend/ en {args.proyecto.resolve()}")
    generar(args.proyecto.resolve(), args.salida.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
