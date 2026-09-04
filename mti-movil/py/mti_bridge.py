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
from typing import Any

from mticore.compare import ComparisonError, compare_families
from mticore.context import ContextError, compare_contexts
from mticore.midi import MidiParseError, parse_midi
from mticore.mti import MTIError, build_mti_graph
from mticore.portable import PortableMTIError, portable_document_from_graph
from mticore.version import SOFTWARE_VERSION

# Errores que representan una entrada inválida del usuario, no un fallo del
# programa. Se comunican como mensaje legible; cualquier otra excepción sube.
_INPUT_ERRORS = (
    ComparisonError,
    ContextError,
    MidiParseError,
    MTIError,
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
