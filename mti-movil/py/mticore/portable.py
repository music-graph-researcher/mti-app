"""Formato portable MTI 1.1 basado en N(G) = {(h, u, v)}."""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from .analysis import derive_form_analysis
from .compare import ComparisonError
from .context import ContextError, attach_context, normalize_context
from .version import SOFTWARE_VERSION


FORMAT_NAME = "MTI"
FORMAT_VERSION = "1.1"
REPRESENTATION = "normalized_family"
PROFILE_ID = "Pmot"
PROFILE_VERSION = "1.0"
_RATIONAL = re.compile(r"^(0|[1-9][0-9]*)(/[1-9][0-9]*)?$")


class PortableMTIError(ValueError):
    pass


def _nonempty_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PortableMTIError(f"{field} debe ser un texto no vacío")


def _validate_provenance(provenance: Any) -> None:
    if provenance is None:
        return
    if not isinstance(provenance, dict):
        raise PortableMTIError("provenance debe ser un objeto")
    allowed = {"source_format", "source_filename", "adapter", "p_ton", "generator"}
    unknown = set(provenance) - allowed
    if unknown:
        raise PortableMTIError(f"Campos de procedencia desconocidos: {', '.join(sorted(unknown))}")
    for field in ("source_format", "source_filename"):
        if field in provenance:
            _nonempty_text(provenance[field], f"provenance.{field}")
    for field in ("adapter", "generator"):
        value = provenance.get(field)
        if value is None:
            continue
        if not isinstance(value, dict) or set(value) != ({"id", "version"} if field == "adapter" else {"name", "version"}):
            required = "id y version" if field == "adapter" else "name y version"
            raise PortableMTIError(f"provenance.{field} debe contener exactamente {required}")
        _nonempty_text(value["id" if field == "adapter" else "name"], f"provenance.{field}")
        _nonempty_text(value["version"], f"provenance.{field}.version")
    p_ton = provenance.get("p_ton")
    if p_ton is not None:
        if not isinstance(p_ton, dict) or set(p_ton) != {"value", "encoding"}:
            raise PortableMTIError("provenance.p_ton debe contener exactamente value y encoding")
        if type(p_ton["value"]) is not int or not 0 <= p_ton["value"] <= 127:
            raise PortableMTIError("provenance.p_ton.value debe ser un entero entre 0 y 127")
        if p_ton["encoding"] != "midi_note_number":
            raise PortableMTIError("provenance.p_ton.encoding debe ser 'midi_note_number'")


def _exact(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _fraction_payload(value: Fraction) -> dict[str, str | float]:
    return {"exact": _exact(value), "value": float(value)}


def _coordinate(value: Any, field: str, index: int) -> Fraction:
    if not isinstance(value, str) or not _RATIONAL.fullmatch(value):
        raise PortableMTIError(f"Evento {index}: {field} debe ser una fracción canónica como '0', '1' o '3/8'")
    result = Fraction(value)
    if _exact(result) != value:
        raise PortableMTIError(f"Evento {index}: {field} debe estar reducida a su forma canónica ({_exact(result)})")
    return result


def validate_portable_document(document: Any) -> list[tuple[int, Fraction, Fraction]]:
    if not isinstance(document, dict):
        raise PortableMTIError("El documento MTI debe ser un objeto JSON")
    unknown = set(document) - {"format", "format_version", "representation", "profile", "normalized_family", "provenance", "context"}
    if unknown:
        raise PortableMTIError(f"Campos MTI desconocidos: {', '.join(sorted(unknown))}")
    if document.get("format") != FORMAT_NAME:
        raise PortableMTIError("El campo format debe ser 'MTI'")
    if document.get("format_version") != FORMAT_VERSION:
        raise PortableMTIError(f"Solo se admite format_version '{FORMAT_VERSION}'")
    if document.get("representation") != REPRESENTATION:
        raise PortableMTIError(f"representation debe ser '{REPRESENTATION}'")
    profile = document.get("profile")
    if not isinstance(profile, dict) or profile.get("id") != PROFILE_ID:
        raise PortableMTIError("El perfil portable debe ser Pmot")
    if set(profile) - {"id", "profile_version"}:
        raise PortableMTIError("El objeto profile contiene campos desconocidos")
    if profile.get("profile_version") != PROFILE_VERSION:
        raise PortableMTIError(f"Solo se admite Pmot profile_version '{PROFILE_VERSION}'")
    family = document.get("normalized_family")
    if not isinstance(family, list) or not family:
        raise PortableMTIError("normalized_family debe ser una lista no vacía")

    descriptors = []
    seen = set()
    for index, item in enumerate(family, start=1):
        if not isinstance(item, dict):
            raise PortableMTIError(f"Evento {index}: el descriptor debe ser un objeto")
        if set(item) != {"h", "u", "v"}:
            raise PortableMTIError(f"Evento {index}: el descriptor debe contener exactamente h, u y v")
        h = item.get("h")
        if type(h) is not int:
            raise PortableMTIError(f"Evento {index}: h debe ser un entero")
        u = _coordinate(item.get("u"), "u", index)
        v = _coordinate(item.get("v"), "v", index)
        if not 0 <= u < v <= 1:
            raise PortableMTIError(f"Evento {index}: debe cumplirse 0 ≤ u < v ≤ 1")
        descriptor = (h, u, v)
        if descriptor in seen:
            raise PortableMTIError(f"Evento {index}: descriptor duplicado")
        seen.add(descriptor)
        descriptors.append(descriptor)
    if min(item[1] for item in descriptors) != 0:
        raise PortableMTIError("La familia debe contener al menos un ataque u = 0")
    if max(item[2] for item in descriptors) != 1:
        raise PortableMTIError("La familia debe contener al menos una terminación v = 1")
    _validate_provenance(document.get("provenance"))
    try:
        normalize_context(
            document.get("context"),
            [{"h": h, "u": {"exact": _exact(u)}, "v": {"exact": _exact(v)}} for h, u, v in descriptors],
        )
    except (ContextError, ComparisonError) as exc:
        raise PortableMTIError(str(exc)) from exc
    return sorted(descriptors, key=lambda item: (item[1], item[2], item[0]))


def graph_from_portable(document: dict[str, Any], filename: str = "motivo.mti.json") -> dict[str, Any]:
    descriptors = validate_portable_document(document)
    times = sorted({item[1] for item in descriptors} | {item[2] for item in descriptors})
    time_index = {time: index for index, time in enumerate(times)}
    sync_nodes = [
        {
            "id": f"theta-{index}",
            "kind": "sync",
            "index": index,
            "normalized": _fraction_payload(time),
        }
        for index, time in enumerate(times)
    ]
    event_nodes = []
    normalized_family = []
    canonical_events = []
    for index, (h, u, v) in enumerate(descriptors, start=1):
        onset_index, offset_index = time_index[u], time_index[v]
        event_nodes.append(
            {
                "id": f"event-{index}",
                "kind": "event",
                "index": index,
                "relative_pitch": h,
                "relative_pitch_class": h % 12,
                "onset_index": onset_index,
                "offset_index": offset_index,
                "onset_normalized": _fraction_payload(u),
                "offset_normalized": _fraction_payload(v),
                "duration_normalized": _fraction_payload(v - u),
            }
        )
        normalized_family.append({"h": h, "u": _fraction_payload(u), "v": _fraction_payload(v)})
        canonical_events.append([onset_index, offset_index, h])

    edges = []
    temporal_word = []
    for index, (left, right) in enumerate(zip(times, times[1:])):
        weight = right - left
        temporal_word.append(_exact(weight))
        edges.append({"id": f"temporal-{index}", "type": "temporal", "source": f"theta-{index}", "target": f"theta-{index + 1}", "weight": _fraction_payload(weight)})
    for event in event_nodes:
        edges.extend(
            [
                {"id": f"onset-{event['index']}", "type": "onset", "source": f"theta-{event['onset_index']}", "target": event["id"]},
                {"id": f"offset-{event['index']}", "type": "offset", "source": event["id"], "target": f"theta-{event['offset_index']}"},
            ]
        )
    provenance = document.get("provenance") if isinstance(document.get("provenance"), dict) else {}
    p_ton = provenance.get("p_ton") if isinstance(provenance.get("p_ton"), dict) else {}
    tonic = p_ton.get("value") if type(p_ton.get("value")) is int else None
    result = {
        "profile": PROFILE_ID,
        "source": {
            "filename": filename,
            "source_format": "mti_json",
            "coordinate_mode": "normalized",
            "midi_format": None,
            "tracks": None,
            "division": None,
            "division_mode": None,
            "input_events": len(descriptors),
            "reduced_events": len(descriptors),
            "duplicates_removed": 0,
            "start_tick": None,
            "end_tick": None,
            "span_ticks": None,
            "provenance": provenance,
        },
        "parameters": {"tonic_pitch": tonic},
        "source_annotations": {
            "structural": False,
            "description": "La procedencia portable no forma parte del grafo, la firma ni la comparación MTI.",
            "sync": [],
            "events": [],
        },
        "nodes": {"sync": sync_nodes, "events": event_nodes},
        "edges": edges,
        "normalized_family": normalized_family,
        "canonical_signature": {"m": len(times) - 1, "R": len(descriptors), "temporal_word": temporal_word, "event_descriptors": sorted(canonical_events)},
        "warnings": [],
    }
    result["form_analysis"] = derive_form_analysis(sync_nodes, event_nodes)
    return attach_context(result, document.get("context"))


def portable_document_from_graph(graph: dict[str, Any]) -> dict[str, Any]:
    source = graph.get("source", {})
    inherited = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
    source_format = inherited.get("source_format") or source.get("source_format", "midi")
    provenance = {
        "source_format": source_format,
        "source_filename": inherited.get("source_filename") or source.get("filename", "motivo.mid"),
        "generator": {"name": "MTI web", "version": SOFTWARE_VERSION},
    }
    if isinstance(inherited.get("adapter"), dict):
        provenance["adapter"] = dict(inherited["adapter"])
    elif source_format == "midi":
        provenance["adapter"] = {"id": "midi", "version": "1.0"}
    tonic = graph.get("parameters", {}).get("tonic_pitch")
    if type(tonic) is int:
        provenance["p_ton"] = {"value": tonic, "encoding": "midi_note_number"}
    document = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "representation": REPRESENTATION,
        "profile": {"id": PROFILE_ID, "profile_version": PROFILE_VERSION},
        "normalized_family": [
            {"h": item["h"], "u": item["u"]["exact"], "v": item["v"]["exact"]}
            for item in graph["normalized_family"]
        ],
        "provenance": provenance,
    }
    if isinstance(graph.get("context"), dict):
        document["context"] = graph["context"]
    return document
