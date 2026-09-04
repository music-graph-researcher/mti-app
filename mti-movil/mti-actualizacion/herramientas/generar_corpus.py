"""Genera los datos de corpus que la app lleva incorporados.

El análisis de corpus (matriz 50x50, jerarquía, familias, asociaciones) usa
multiproceso, que Pyodide no soporta, y de todos modos no tiene sentido
recalcularlo en un móvil: el corpus es fijo. Se calcula aquí una vez y la app
solo lo muestra.

Uso, desde la raíz del proyecto MTI:

    python3 ruta/a/mti-movil/herramientas/generar_corpus.py \
        --proyecto . --salida ruta/a/mti-movil/corpus

Produce dos archivos:

  corpus.json    los 50 documentos portables + metadatos. La app los carga para
                 poder comparar un motivo nuevo contra el corpus, en vivo y por
                 pares.
  informe.json   el análisis de corpus ya calculado, recortado a lo que la
                 interfaz móvil muestra.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _valor(celda: Any) -> float | None:
    """Se queda con el flotante y descarta la fracción exacta.

    Las matrices exactas ocupan tres veces más y la interfaz solo las usa para
    pintar un mapa de calor. Los valores exactos siguen estando donde importan:
    en cada comparación que la app calcula en vivo.
    """

    if isinstance(celda, dict):
        return celda.get("value")
    return celda


def _matriz(matriz: Any) -> list[list[float | None]]:
    return [[_valor(c) for c in fila] for fila in matriz]


def _item(registro: dict[str, Any]) -> dict[str, Any]:
    meta = registro.get("metadata") or {}
    return {
        "id": registro.get("id"),
        "obra": meta.get("work"),
        "compositor": meta.get("composer"),
        "sector": registro.get("advertising_type"),
        "textura": meta.get("texture"),
        "tonica": meta.get("tonic_pitch"),
        "familia": registro.get("family"),
        "silueta": _valor(registro.get("silhouette")),
    }


def generar(proyecto: Path, salida: Path) -> None:
    sys.path.insert(0, str(proyecto))
    from backend.corpus_analysis import analyze_graph_corpus
    from backend.portable import graph_from_portable

    raiz = proyecto / "nice-dataset-main"
    metadatos = json.loads((raiz / "metadata.json").read_text(encoding="utf-8"))["items"]

    documentos: dict[str, Any] = {}
    registros = []
    for nombre, info in metadatos.items():
        documento = json.loads((raiz / nombre).read_text(encoding="utf-8"))
        documentos[nombre] = documento
        registros.append(
            {
                "id": info["id"],
                "graph": graph_from_portable(documento, nombre),
                "advertising_type": info["advertising_type"],
                "label": info["work"],
                "metadata": info,
            }
        )

    salida.mkdir(parents=True, exist_ok=True)

    corpus = {
        "fuente": "nice-dataset",
        "obras": len({i["work"] for i in metadatos.values()}),
        "registros": len(metadatos),
        "items": metadatos,
        "documents": documentos,
    }
    (salida / "corpus.json").write_text(
        json.dumps(corpus, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    bruto = analyze_graph_corpus(registros)
    informe = {
        "protocolo": bruto["protocol"],
        "parametros": bruto["parameters"],
        "resumen": bruto["summary"],
        "items": [_item(r) for r in bruto["items"]],
        "disimilitud_relativa": _matriz(bruto["relative_dissimilarity_matrix"]),
        "familias": bruto["clustering"],
        "vecindades": bruto["neighborhoods"],
        "asociaciones": bruto["advertising_associations"],
        "jerarquia": bruto["hierarchy"],
    }
    (salida / "informe.json").write_text(
        json.dumps(informe, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    for nombre in ("corpus.json", "informe.json"):
        peso = (salida / nombre).stat().st_size / 1024
        print(f"  {nombre:<16} {peso:7.1f} KB")
    print(f"  {len(metadatos)} registros · {corpus['obras']} obras · "
          f"silueta {bruto['summary'].get('silhouette'):.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proyecto", type=Path, default=Path("."),
                        help="raíz del repositorio MTI (donde está backend/)")
    parser.add_argument("--salida", type=Path, required=True,
                        help="carpeta corpus/ de la app móvil")
    args = parser.parse_args()

    if not (args.proyecto / "backend" / "corpus_analysis.py").is_file():
        parser.error(f"No encuentro backend/ en {args.proyecto.resolve()}")
    generar(args.proyecto.resolve(), args.salida.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
