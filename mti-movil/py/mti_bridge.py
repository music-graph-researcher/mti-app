"""Puente entre la interfaz móvil y el núcleo MTI.

La interfaz nunca calcula nada: lee el MIDI, deja elegir el fragmento y la
referencia tonal, y delega en `mticore`, que es una copia literal de `backend/`.
Así el resultado en el móvil coincide con el de `python3 -m backend.server`.

Todas las funciones devuelven una cadena JSON. Es deliberado: evita convertir
objetos Python a JavaScript a través de proxies y mantiene el contrato de datos
idéntico al de la API HTTP del proyecto.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import json
from fractions import Fraction
from typing import Any

from mticore.compare import (
    ComparisonError,
    compare_families,
    compare_families_compact,
)
from mticore.context import ContextError, compare_contexts
from mticore.hierarchy import (
    HierarchyError,
    constitute,
    construct_eventive_preimage,
    foundation_fixtures,
    verify_lift_operator,
)
from mticore.midi import MidiParseError, parse_midi
from mticore.mti import MTIError, build_mti_graph
from mticore.operational_topology import compare_topologies
from mticore.operations import (
    OperationalError,
    canonical_fixtures,
    reachability_request,
    search_request,
    trajectory_request,
)
from mticore.portable import (
    PortableMTIError,
    graph_from_portable,
    portable_document_from_graph,
)
from mticore.version import SOFTWARE_VERSION

# Errores que representan una entrada inválida del usuario, no un fallo del
# programa. Se comunican como mensaje legible; cualquier otra excepción sube.
_INPUT_ERRORS = (
    ComparisonError,
    ContextError,
    HierarchyError,
    MidiParseError,
    MTIError,
    OperationalError,
    PortableMTIError,
    ValueError,
    KeyError,
    TypeError,
)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _fail(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _decode(data_b64: str) -> bytes:
    try:
        return base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"No se pudo leer el archivo recibido: {exc}") from exc


def version() -> str:
    """Versión del núcleo MTI incrustado, para mostrarla en la interfaz."""

    return _ok({"software_version": SOFTWARE_VERSION})


def inspect(data_b64: str) -> str:
    """Lee el MIDI y devuelve sus notas para dibujar el piano-roll.

    No construye el grafo. Es la vista previa sobre la que el usuario decide el
    fragmento, y debe seguir siendo barata incluso con obras completas.

    El índice de cada nota es su posición en el orden canónico de `parse_midi`.
    La interfaz devuelve luego esos mismos índices para fijar el fragmento, de
    modo que lo analizado es exactamente lo que se ha visto seleccionado.
    """

    try:
        raw = _decode(data_b64)
        midi = parse_midi(raw)
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    notes = [
        {
            "i": index,
            "pitch": note.pitch,
            "onset": note.onset,
            "duration": note.duration,
            "track": note.track,
            "channel": note.channel,
        }
        for index, note in enumerate(midi.notes)
    ]
    return _ok(
        {
            "format": midi.format,
            "division": midi.division,
            "tracks": midi.tracks,
            "notes": notes,
            "tracks_present": sorted({n["track"] for n in notes}),
            "channels_present": sorted({n["channel"] for n in notes}),
            "warnings": list(midi.warnings),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    )


def analyze(data_b64: str, tonic: int, indices_json: str, filename: str) -> str:
    """Construye el grafo MTI del fragmento indicado.

    `indices_json` es la lista de índices de nota seleccionados en la vista
    previa. Una lista vacía significa el archivo completo, que es el alcance
    descrito en el documento fundacional.
    """

    try:
        raw = _decode(data_b64)
        midi = parse_midi(raw)
        indices = json.loads(indices_json)
        if not isinstance(indices, list):
            raise ValueError("La selección debe ser una lista de índices")

        if indices:
            total = len(midi.notes)
            chosen = []
            for value in indices:
                index = int(value)
                if not 0 <= index < total:
                    raise ValueError(f"Índice de nota fuera de rango: {index}")
                chosen.append(midi.notes[index])
            fragment = dataclasses.replace(midi, notes=tuple(chosen))
        else:
            fragment = midi

        result = build_mti_graph(fragment, int(tonic), filename)
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    # Misma trazabilidad que sirve `backend/server.py`, adaptada al hecho de que
    # aquí el fragmento puede ser un subconjunto elegido por el usuario.
    result["source"]["reproducibility"] = {
        "app_version": SOFTWARE_VERSION,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "input_bytes": len(raw),
        "exact_arithmetic": "fractions.Fraction",
        "selected_note_indices": len(indices) if indices else len(midi.notes),
        "file_note_count": len(midi.notes),
        "segmentation": "seleccion_manual" if indices else "archivo_completo",
    }
    return _ok({"result": result})


def portable(result_json: str) -> str:
    """Convierte un análisis en el documento `.mti.json` portable 1.1."""

    try:
        document = portable_document_from_graph(json.loads(result_json))
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))
    return _ok({"document": document})


def compare(family_a_json: str, family_b_json: str, parameters_json: str) -> str:
    """Calcula `Dγ` entre dos familias normalizadas."""

    try:
        parameters = json.loads(parameters_json)
        comparison = compare_families(
            json.loads(family_a_json), json.loads(family_b_json), parameters
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))
    return _ok({"comparison": comparison})


def compare_with_context(
    family_a_json: str,
    family_b_json: str,
    parameters_json: str,
    context_a_json: str,
    context_b_json: str,
) -> str:
    """Añade la lectura contextual §3.6 sin agregarla a `Dγ`.

    Los bloques melódico, armónico y rítmico-métrico se devuelven separados,
    tal como exige la tesis: no se combinan en un escalar único.
    """

    structural = compare(family_a_json, family_b_json, parameters_json)
    payload = json.loads(structural)
    if not payload.get("ok"):
        return structural

    try:
        contextual = compare_contexts(
            json.loads(family_a_json),
            json.loads(family_b_json),
            json.loads(context_a_json),
            json.loads(context_b_json),
            json.loads(parameters_json),
        )
    except _INPUT_ERRORS as exc:
        payload["contextual_error"] = str(exc)
        return json.dumps(payload, ensure_ascii=False)

    payload["contextual"] = contextual
    return json.dumps(payload, ensure_ascii=False)


# ─────────────────────────── Corpus publicitario ───────────────────────────
#
# El corpus es fijo: 25 obras clásicas empleadas en publicidad, cada una en
# textura armónica y melódica. Se carga una sola vez y se conserva en memoria,
# porque la app lo consulta en cada análisis.
#
# La etiqueta de sector NUNCA entra en el cálculo. Es una etiqueta externa que
# se muestra junto al resultado, como en `backend/corpus_comparison.py`.

_CORPUS: list[dict[str, Any]] = []


def load_corpus(corpus_json: str) -> str:
    """Convierte los documentos portables del corpus en familias comparables."""

    global _CORPUS
    try:
        paquete = json.loads(corpus_json)
        metadatos = paquete["items"]
        documentos = paquete["documents"]
        cargado = []
        for nombre, info in metadatos.items():
            grafo = graph_from_portable(documentos[nombre], nombre)
            cargado.append(
                {
                    "id": info["id"],
                    "obra": info["work"],
                    "compositor": info["composer"],
                    "sector": info["advertising_type"],
                    "textura": info["texture"],
                    "tonica": info["tonic_pitch"],
                    "familia": grafo["normalized_family"],
                }
            )
    except _INPUT_ERRORS as exc:
        return _fail(f"No se pudo cargar el corpus: {exc}")

    _CORPUS = cargado
    sectores = sorted({r["sector"] for r in cargado})
    return _ok(
        {
            "registros": len(cargado),
            "obras": len({r["obra"] for r in cargado}),
            "sectores": sectores,
        }
    )


def rank_corpus(family_json: str, parameters_json: str) -> str:
    """Sitúa una familia frente a los registros del corpus, uno a uno.

    Son comparaciones por pares, que es lo único que define el marco. No hay
    aquí ningún análisis de corpus: el ranking ordena distancias, no clasifica.
    Se usa la variante compacta porque no hace falta la explicación evento a
    evento de cincuenta comparaciones.
    """

    if not _CORPUS:
        return _fail("El corpus no está cargado")
    try:
        consulta = json.loads(family_json)
        parametros = json.loads(parameters_json)
        filas = []
        for registro in _CORPUS:
            resultado = compare_families_compact(consulta, registro["familia"], parametros)
            filas.append(
                {
                    "id": registro["id"],
                    "obra": registro["obra"],
                    "compositor": registro["compositor"],
                    "sector": registro["sector"],
                    "textura": registro["textura"],
                    "eventos": len(registro["familia"]),
                    "distancia": resultado["distance"],
                    "relativa": resultado["relative_index"]["dissimilarity"],
                    "componentes": resultado["components"],
                }
            )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    filas.sort(key=lambda f: f["relativa"]["value"])
    return _ok({"filas": filas, "parametros": parametros})


# ─────────────────────── Jerarquía constitutiva (cap. 6) ───────────────────────
#
# Las cuatro operaciones que expone la interfaz del 8003. La app móvil sustituye
# los cuadros de JSON del escritorio por selectores, pero el contrato con el
# núcleo es idéntico: mismas funciones, mismos argumentos.

CONFIGURACION_EJEMPLO = {
    "level": 0,
    "occurrences": [
        {"id": "e1", "state": {"pitch": 0, "onset": "0", "duration": "1/4", "articulation": "alpha0"}},
        {"id": "e2", "state": {"pitch": 2, "onset": "1/4", "duration": "1/8", "articulation": "alpha0"}},
        {"id": "e3", "state": {"pitch": 4, "onset": "1/2", "duration": "1/4", "articulation": "alpha0"}},
        {"id": "e4", "state": {"pitch": 7, "onset": "3/4", "duration": "1/4", "articulation": "alpha0"}},
    ],
    "relations": {"type": "B(M)"},
    "auxiliary_data": {"p_ton": 0},
}


def _exacto(coordenada: Any) -> Fraction:
    """Toma la fracción exacta de un descriptor, nunca su aproximación decimal."""

    if isinstance(coordenada, dict):
        return Fraction(str(coordenada["exact"]))
    return Fraction(str(coordenada))


def configuration_from_family(family_json: str) -> str:
    """Construye una configuración basal Ξ₀ a partir de una familia normalizada.

    Es la lectura inversa de la constitución: cada descriptor `(h, u, v)` se
    escribe como una ocurrencia basal con altura `h`, ataque `u` y duración
    `v − u`, sobre `p_ton = 0` porque `h` ya es altura relativa.

    Permite alimentar el laboratorio del capítulo 6 con un motivo analizado en la
    propia app, en vez de teclear JSON en un móvil.
    """

    try:
        familia = json.loads(family_json)
        ocurrencias = []
        for indice, descriptor in enumerate(familia, start=1):
            u = _exacto(descriptor["u"])
            v = _exacto(descriptor["v"])
            if v <= u:
                raise ValueError(f"El descriptor {indice} no tiene duración positiva")
            ocurrencias.append(
                {
                    "id": f"e{indice}",
                    "state": {
                        "pitch": int(descriptor["h"]),
                        "onset": str(u),
                        "duration": str(v - u),
                        "articulation": "alpha0",
                    },
                }
            )
        if not ocurrencias:
            raise ValueError("La familia está vacía")
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    return _ok(
        {
            "configuration": {
                "level": 0,
                "occurrences": ocurrencias,
                "relations": {"type": "B(M)"},
                "auxiliary_data": {"p_ton": 0},
            },
            "motif": {
                "events": [
                    [int(d["h"]), str(_exacto(d["u"])), str(_exacto(d["v"]))] for d in familia
                ]
            },
        }
    )


def hierarchy_fixtures() -> str:
    """Ejecuta las diecinueve comprobaciones fundacionales de la transición 0→1."""

    try:
        return _ok({"report": foundation_fixtures()})
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))


def hierarchy_constitute(configuration_json: str) -> str:
    """Aplica A₀→₁ a una configuración basal y devuelve el testigo."""

    try:
        resultado = constitute(
            {"map_id": "A_0_1", "version": "1.0.0"}, json.loads(configuration_json)
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))
    return _ok({"result": resultado})


def hierarchy_preimage(motif_json: str) -> str:
    """Construye una preimagen eventiva Ξ_X tal que A₀→₁(Ξ_X) = X."""

    try:
        registro = construct_eventive_preimage(json.loads(motif_json))
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))
    return _ok({"record": registro})


def hierarchy_lift(
    configuration_json: str, operator: str, descriptor_json: str, delta_json: str
) -> str:
    """Verifica que el diagrama de elevación de un operador conmuta."""

    try:
        delta = json.loads(delta_json)
        resultado = verify_lift_operator(
            json.loads(configuration_json),
            operator,
            json.loads(descriptor_json),
            delta,
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))
    return _ok({"result": resultado})


# ────────────────────── Topología operacional (cap. 5) ──────────────────────
#
# La búsqueda produce un grafo explorado de medio megabyte y el informe de
# topología casi tres. Nada de eso tiene por qué cruzar al navegador: se guarda
# aquí, del lado de Python, y a la interfaz solo viajan los resúmenes que
# muestra. El informe completo se entrega únicamente si el usuario lo exporta.

_SESION_OP: dict[str, Any] = {"busqueda": None, "envelope": None, "topologia": None}

ENVOLVENTE_MOVIL = {
    "max_steps": 4,
    "max_nodes": 400,
    "max_paths": 64,
    "timeout_ms": 9000,
    "pitch_deltas": [-2, -1, 1, 2],
    "onset_deltas": ["-1/4", "-1/8", "1/8", "1/4"],
    "offset_deltas": ["-1/4", "-1/8", "1/8", "1/4"],
    "include_identity": False,
    "exclude_stationary": False,
}


def operations_fixtures() -> str:
    """Casos canónicos del capítulo 5."""

    try:
        return _ok({"fixtures": canonical_fixtures()})
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))


def operations_trajectory(
    source_json: str, target_json: str, actions_json: str, parameters_json: str
) -> str:
    """Evalúa una trayectoria y la contrasta con `Dγ` (§5.9.1)."""

    try:
        resultado = trajectory_request(
            {
                "source": json.loads(source_json),
                "target": json.loads(target_json),
                "actions": json.loads(actions_json),
                "parameters": json.loads(parameters_json),
            }
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))
    return _ok(
        {
            "coste": resultado.get("cost"),
            "pasos": resultado.get("step_count"),
            "reducida": resultado.get("reduced"),
            "secuencia": resultado.get("qualitative_sequence"),
            "alcanza": resultado.get("reaches_requested_target"),
            "comparacion": resultado.get("comparison"),
        }
    )


def _paso_legible(paso: dict[str, Any]) -> dict[str, Any]:
    """Describe una acción en una línea: «del h=0 u=0 v=1/4», «h Δ=+1», etc."""

    accion = paso.get("action") or {}
    tipo = accion.get("kind", "?")
    evento = accion.get("event") or {}
    partes = []
    if "h" in evento:
        partes.append(f"h={evento['h']}")
    for coordenada in ("u", "v"):
        valor = evento.get(coordenada)
        if isinstance(valor, dict):
            partes.append(f"{coordenada}={valor.get('exact')}")
    if accion.get("delta") is not None:
        partes.append(f"Δ={accion['delta']}")
    return {
        "accion": f"{tipo} {' '.join(partes)}".strip(),
        "coste": paso.get("cost"),
        "renormaliza": bool((paso.get("normalization") or {}).get("effective")),
    }


def operations_reachability(source_json: str, target_json: str, parameters_json: str) -> str:
    """Testigo constructivo de alcanzabilidad. Su coste no se presenta como δ_T."""

    try:
        resultado = reachability_request(
            {
                "source": json.loads(source_json),
                "target": json.loads(target_json),
                "parameters": json.loads(parameters_json),
            }
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    pasos = resultado.get("steps") or []
    return _ok(
        {
            "coste": resultado.get("cost"),
            "pasos": resultado.get("step_count"),
            "cota": resultado.get("bound"),
            "dentro_de_cota": resultado.get("within_bound"),
            "alcanza": resultado.get("reaches_requested_target"),
            "distancia_estatica": (resultado.get("static_distance") or {}).get("distance"),
            "declaracion": resultado.get("statement"),
            # Solo los primeros pasos: el testigo completo puede tener decenas.
            "muestra_pasos": [_paso_legible(p) for p in pasos[:12]],
            "pasos_omitidos": max(0, len(pasos) - 12),
        }
    )


def operations_search(
    source_json: str, target_json: str, parameters_json: str, envelope_json: str
) -> str:
    """Materializa el multigrafo finito `G_R` dentro de la envolvente declarada."""

    try:
        objetivo = json.loads(target_json)
        envolvente = dict(ENVOLVENTE_MOVIL)
        envolvente.update(json.loads(envelope_json) or {})
        envolvente.setdefault("insertions", objetivo.get("events", []))
        resultado = search_request(
            {
                "source": json.loads(source_json),
                "target": objetivo,
                "parameters": json.loads(parameters_json),
                "mode": "TARGET_GUIDED",
                "envelope": envolvente,
            }
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    _SESION_OP["busqueda"] = resultado
    _SESION_OP["envelope"] = envolvente
    _SESION_OP["topologia"] = None

    proceso = resultado.get("process_analysis") or {}
    return _ok(
        {
            "estado": resultado.get("status"),
            "truncado_por": resultado.get("truncated_by"),
            "mejor_coste": resultado.get("best_cost"),
            "exacto_en_restriccion": resultado.get("exact_within_restriction"),
            "nodos": resultado.get("nodes_expanded"),
            "aristas": resultado.get("edges_generated"),
            "pasos_mejor_camino": len(resultado.get("best_path") or []),
            "declaracion": resultado.get("statement"),
            "ms": resultado.get("elapsed_ms"),
            "procesos": {
                "caminos_optimos": len(proceso.get("optimal_reduced_paths") or []),
                "clase": proceso.get("process_class_status"),
                "diamantes": len(proceso.get("commutative_diamonds") or []),
                "ramificacion": len(proceso.get("branching_states") or []),
                "reconvergencia": len(proceso.get("reconvergence_states") or []),
            },
        }
    )


def operations_topology(parameters_json: str) -> str:
    """Compara la topología estructural y la operacional sobre el mismo `G_R`."""

    busqueda = _SESION_OP.get("busqueda")
    if not busqueda:
        return _fail("Primero hay que materializar G_R con la búsqueda")
    try:
        informe = compare_topologies(
            {
                "explored_graph": busqueda.get("explored_graph"),
                "search_envelope": _SESION_OP.get("envelope"),
                "parameters": json.loads(parameters_json),
            }
        )
    except _INPUT_ERRORS as exc:
        return _fail(str(exc))

    _SESION_OP["topologia"] = informe
    return _ok(
        {
            "estado": informe.get("topology_status"),
            "resumen": informe.get("validation_summary"),
            "metrica": informe.get("metric_checks"),
            "conectividad": informe.get("strong_connectivity"),
            "comparacion": informe.get("comparison"),
        }
    )


def operations_report() -> str:
    """Devuelve el informe completo de topología, solo cuando se exporta."""

    informe = _SESION_OP.get("topologia")
    if not informe:
        return _fail("Todavía no hay informe de topología")
    return json.dumps({"ok": True, "report": informe}, ensure_ascii=False)
