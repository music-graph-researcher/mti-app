"""Extrae el informe de validación E3–E6 que la app muestra.

La validación del 8004 se ejecuta sobre el corpus JKU-PDD (384 MB) y usa
multiproceso: no se puede recalcular en un móvil, ni tendría sentido hacerlo.
Una corrida certificada se exhibe, no se rehace.

El `report.json` completo son 2,1 MB de volcado para auditar en un ordenador.
Este guion se queda con lo que una pantalla de móvil puede leer —métricas,
pliegues, ablaciones y trazabilidad— y deja fuera las listas por consulta.

Uso, desde la raíz del proyecto MTI:

    python3 ruta/a/mti-movil/herramientas/generar_validacion.py \
        --corrida runs/<run_id> --salida ruta/a/mti-movil/validacion
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def _metricas(origen: dict[str, Any]) -> dict[str, Any]:
    return {clave: origen.get(clave) for clave in ("mAP", "MRR", "Recall@1", "Recall@10")}


def _ablacion(entrada: dict[str, Any]) -> dict[str, Any]:
    intervalo = (entrada.get("confidence_interval_95") or {}).get("mAP") or {}
    return {
        "id": entrada.get("id"),
        "etiqueta": entrada.get("label"),
        "estatus": entrada.get("metric_status"),
        "mAP": entrada.get("pooled_mAP"),
        "MRR": entrada.get("pooled_MRR"),
        "delta_mAP": entrada.get("delta_mAP_vs_full"),
        "ic95_delta_mAP": [intervalo.get("lower"), intervalo.get("upper")],
    }


def _pliegue(retrieval: dict[str, Any], seleccion: dict[str, Any]) -> list[dict[str, Any]]:
    elegidos = {p["fold_id"]: p for p in seleccion.get("per_fold", [])}
    pliegues = []
    for fold in retrieval.get("per_fold", []):
        elegido = elegidos.get(fold.get("fold_id"), {})
        pliegues.append(
            {
                "id": fold.get("fold_id"),
                "grupo_test": fold.get("test_group"),
                "consultas": fold.get("eligible_queries"),
                "metricas": _metricas(fold),
                "parametros": elegido.get("selected_parameters"),
                "candidatos": elegido.get("candidate_count"),
                "mAP_desarrollo": elegido.get("selected_development_mAP"),
            }
        )
    return pliegues


def generar(corrida: Path, salida: Path) -> None:
    informe = json.loads((corrida / "report.json").read_text(encoding="utf-8"))
    configuracion = json.loads((corrida / "config.json").read_text(encoding="utf-8"))
    reproducibilidad = informe.get("reproducibility", {})
    git = reproducibilidad.get("git", {})

    compacto = {
        "run_id": informe.get("run_id"),
        "estatus": informe.get("evidence_status"),
        "afirmaciones_permitidas": informe.get("empirical_claims_allowed"),
        "corpus": informe.get("corpus"),
        "particion": informe.get("split_strategy"),
        "configuracion": {
            "modo": configuracion.get("mode"),
            "rejilla": configuracion.get("parameter_grid"),
            "recuperacion": configuracion.get("retrieval"),
            "tamano_rejilla": (informe.get("parameter_selection") or {}).get("grid_size"),
        },
        "incertidumbre": informe.get("uncertainty"),
        "metricas_globales": (informe.get("retrieval") or {}).get("pooled_query_metrics"),
        "metricas_macro": (informe.get("retrieval") or {}).get("macro_fold_metrics"),
        "pliegues": _pliegue(
            informe.get("retrieval") or {}, informe.get("parameter_selection") or {}
        ),
        "ablaciones": [
            _ablacion(a)
            for a in ((informe.get("ablations") or {}).get("global") or {}).get("results", [])
        ],
        "avisos": [
            {"tipo": a.get("type"), "mensaje": a.get("message")}
            for a in informe.get("warnings", [])
        ],
        "errores": informe.get("errors", []),
        "trazabilidad": {
            "software": reproducibilidad.get("software"),
            "python": reproducibilidad.get("python"),
            "plataforma": reproducibilidad.get("platform"),
            "commit": git.get("commit"),
            "rama": git.get("branch"),
            "arbol_limpio": not git.get("dirty", False),
            "sha256_arbol": reproducibilidad.get("source_tree_sha256"),
            "sha256_config": reproducibilidad.get("config_sha256"),
            "sha256_manifiesto": informe.get("manifest_sha256"),
            "manifiesto": informe.get("manifest"),
        },
        "duracion_segundos": (informe.get("runtime") or {}).get("elapsed_seconds"),
    }

    salida.mkdir(parents=True, exist_ok=True)
    (salida / "informe.json").write_text(
        json.dumps(compacto, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    resumen = corrida / "summary.md"
    if resumen.is_file():
        shutil.copyfile(resumen, salida / "resumen.md")

    for nombre in ("informe.json", "resumen.md"):
        ruta = salida / nombre
        if ruta.is_file():
            print(f"  {nombre:<16} {ruta.stat().st_size / 1024:7.1f} KB")
    print(f"  corrida {compacto['run_id']} · {compacto['estatus']} · "
          f"{len(compacto['pliegues'])} pliegues · {len(compacto['ablaciones'])} ablaciones")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrida", type=Path, required=True,
                        help="carpeta runs/<run_id> con report.json y config.json")
    parser.add_argument("--salida", type=Path, required=True,
                        help="carpeta validacion/ de la app móvil")
    args = parser.parse_args()

    if not (args.corrida / "report.json").is_file():
        parser.error(f"No encuentro report.json en {args.corrida.resolve()}")
    generar(args.corrida.resolve(), args.salida.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
