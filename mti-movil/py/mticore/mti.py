"""Construcción del grafo del perfil motívico tonal-temporal de MOTIF2."""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Iterable

from .midi import MidiFileData, MidiNote
from .analysis import derive_form_analysis
from .context import attach_context


class MTIError(ValueError):
    pass


def _fraction_payload(value: Fraction) -> dict[str, str | float]:
    return {
        "exact": str(value.numerator)
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}",
        "value": float(value),
    }


def _deduplicate(notes: Iterable[MidiNote]) -> list[MidiNote]:
    """Pmot identifica eventos que coinciden en (p, tau, d)."""

    unique: dict[tuple[int, int, int], MidiNote] = {}
    for note in notes:
        unique.setdefault((note.pitch, note.onset, note.duration), note)
    return sorted(unique.values(), key=lambda n: (n.onset, n.offset, n.pitch))


def build_mti_graph(midi: MidiFileData, tonic: int, filename: str = "motivo.mid") -> dict[str, Any]:
    if not isinstance(tonic, int) or not 0 <= tonic <= 127:
        raise MTIError("p_ton debe ser una altura MIDI concreta entre 0 y 127")
    if not midi.notes:
        raise MTIError("El archivo no contiene notas completas con duración positiva")

    reduced = _deduplicate(midi.notes)
    times = sorted({n.onset for n in reduced} | {n.offset for n in reduced})
    if len(times) < 2 or times[-1] <= times[0]:
        raise MTIError("No se puede determinar una extensión temporal positiva")
    time_index = {tick: index for index, tick in enumerate(times)}
    start, end = times[0], times[-1]
    span = end - start

    sync_nodes = []
    sync_annotations = []
    for index, tick in enumerate(times):
        normalized = Fraction(tick - start, span)
        sync_nodes.append(
            {
                "id": f"theta-{index}",
                "kind": "sync",
                "index": index,
                "normalized": _fraction_payload(normalized),
            }
        )
        sync_annotations.append({"id": f"theta-{index}", "tick": tick})

    event_nodes = []
    event_annotations = []
    event_descriptors: list[list[int]] = []
    normalized_family = []
    for index, note in enumerate(reduced, start=1):
        onset_index = time_index[note.onset]
        offset_index = time_index[note.offset]
        relative_pitch = note.pitch - tonic
        onset_norm = Fraction(note.onset - start, span)
        offset_norm = Fraction(note.offset - start, span)
        duration_norm = Fraction(note.duration, span)
        event_nodes.append(
            {
                "id": f"event-{index}",
                "kind": "event",
                "index": index,
                "relative_pitch": relative_pitch,
                "relative_pitch_class": relative_pitch % 12,
                "onset_index": onset_index,
                "offset_index": offset_index,
                "onset_normalized": _fraction_payload(onset_norm),
                "offset_normalized": _fraction_payload(offset_norm),
                "duration_normalized": _fraction_payload(duration_norm),
            }
        )
        event_annotations.append(
            {
                "id": f"event-{index}",
                "pitch": note.pitch,
                "onset_tick": note.onset,
                "offset_tick": note.offset,
                "duration_tick": note.duration,
                "attributes": {
                    "track": note.track + 1,
                    "channel": note.channel + 1,
                    "velocity": note.velocity,
                },
            }
        )
        event_descriptors.append([onset_index, offset_index, relative_pitch])
        normalized_family.append(
            {
                "h": relative_pitch,
                "u": _fraction_payload(onset_norm),
                "v": _fraction_payload(offset_norm),
            }
        )

    edges = []
    temporal_word: list[str] = []
    for index in range(len(times) - 1):
        weight = Fraction(times[index + 1] - times[index], span)
        payload = _fraction_payload(weight)
        temporal_word.append(str(payload["exact"]))
        edges.append(
            {
                "id": f"temporal-{index}",
                "type": "temporal",
                "source": f"theta-{index}",
                "target": f"theta-{index + 1}",
                "weight": payload,
            }
        )
    for event in event_nodes:
        edges.append(
            {
                "id": f"onset-{event['index']}",
                "type": "onset",
                "source": f"theta-{event['onset_index']}",
                "target": event["id"],
            }
        )
        edges.append(
            {
                "id": f"offset-{event['index']}",
                "type": "offset",
                "source": event["id"],
                "target": f"theta-{event['offset_index']}",
            }
        )

    duplicate_count = len(midi.notes) - len(reduced)
    warnings = list(midi.warnings)
    if duplicate_count:
        warnings.append(
            f"Pmot identificó {duplicate_count} duplicado(s) exacto(s) en altura, ataque y duración."
        )

    result = {
        "profile": "Pmot",
        "source": {
            "filename": filename,
            "source_format": "midi",
            "coordinate_mode": "ticks",
            "midi_format": midi.format,
            "tracks": midi.tracks,
            "division": midi.division,
            "division_mode": "smpte" if midi.division & 0x8000 else "ticks_per_quarter_note",
            "input_events": len(midi.notes),
            "reduced_events": len(reduced),
            "duplicates_removed": duplicate_count,
            "start_tick": start,
            "end_tick": end,
            "span_ticks": span,
        },
        "parameters": {"tonic_pitch": tonic},
        "source_annotations": {
            "structural": False,
            "description": "Anotaciones de procedencia excluidas del grafo, la firma y la comparación MTI.",
            "sync": sync_annotations,
            "events": event_annotations,
        },
        "nodes": {"sync": sync_nodes, "events": event_nodes},
        "edges": edges,
        "normalized_family": normalized_family,
        "canonical_signature": {
            "m": len(times) - 1,
            "R": len(reduced),
            "temporal_word": temporal_word,
            "event_descriptors": sorted(event_descriptors),
        },
        "warnings": warnings,
    }
    result["form_analysis"] = derive_form_analysis(sync_nodes, event_nodes)
    base_events = []
    for index, note in enumerate(midi.notes, start=1):
        base_events.append(
            {
                "id": f"base-event-{index}",
                "pitch": note.pitch,
                "h": note.pitch - tonic,
                "u": str(Fraction(note.onset - start, span)),
                "v": str(Fraction(note.offset - start, span)),
                "onset_tick": note.onset,
                "offset_tick": note.offset,
                "track": note.track + 1,
                "channel": note.channel + 1,
                "velocity": note.velocity,
            }
        )
    return attach_context(result, base_events=base_events)
