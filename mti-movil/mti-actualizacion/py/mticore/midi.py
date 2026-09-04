"""Lector mínimo y estricto de Standard MIDI Files.

El MTI solo necesita altura, ataque y terminación. Este módulo evita convertir
ticks a segundos: el perfil normaliza el eje temporal y, por tanto, los ticks
son el dominio racional exacto más natural para la entrada MIDI.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque


class MidiParseError(ValueError):
    """El archivo no es un Standard MIDI File válido o soportado."""


@dataclass(frozen=True)
class MidiNote:
    pitch: int
    onset: int
    duration: int
    track: int
    channel: int
    velocity: int

    @property
    def offset(self) -> int:
        return self.onset + self.duration


@dataclass(frozen=True)
class MidiFileData:
    format: int
    division: int
    tracks: int
    notes: tuple[MidiNote, ...]
    warnings: tuple[str, ...]


def _u16(data: bytes, pos: int) -> int:
    if pos + 2 > len(data):
        raise MidiParseError("Final de archivo inesperado")
    return int.from_bytes(data[pos : pos + 2], "big")


def _u32(data: bytes, pos: int) -> int:
    if pos + 4 > len(data):
        raise MidiParseError("Final de archivo inesperado")
    return int.from_bytes(data[pos : pos + 4], "big")


def _vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if pos >= len(data):
            raise MidiParseError("VLQ truncado")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, pos
    raise MidiParseError("VLQ MIDI de más de cuatro bytes")


def _parse_track(track: bytes, track_index: int) -> tuple[list[MidiNote], list[str]]:
    pos = 0
    tick = 0
    running_status: int | None = None
    active: dict[tuple[int, int], Deque[tuple[int, int]]] = defaultdict(deque)
    notes: list[MidiNote] = []
    warnings: list[str] = []

    while pos < len(track):
        delta, pos = _vlq(track, pos)
        tick += delta
        if pos >= len(track):
            raise MidiParseError(f"Evento truncado en la pista {track_index + 1}")

        first = track[pos]
        if first & 0x80:
            status = first
            pos += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise MidiParseError(
                f"Running status sin estado previo en la pista {track_index + 1}"
            )

        if status == 0xFF:
            running_status = None
            if pos >= len(track):
                raise MidiParseError("Metaevento truncado")
            meta_type = track[pos]
            pos += 1
            length, pos = _vlq(track, pos)
            if pos + length > len(track):
                raise MidiParseError("Contenido de metaevento truncado")
            pos += length
            if meta_type == 0x2F:
                break
            continue

        if status in (0xF0, 0xF7):
            running_status = None
            length, pos = _vlq(track, pos)
            if pos + length > len(track):
                raise MidiParseError("Evento SysEx truncado")
            pos += length
            continue

        kind = status & 0xF0
        channel = status & 0x0F
        data_length = 1 if kind in (0xC0, 0xD0) else 2
        if kind < 0x80 or kind > 0xE0 or pos + data_length > len(track):
            raise MidiParseError(f"Mensaje MIDI no válido en la pista {track_index + 1}")
        values = track[pos : pos + data_length]
        pos += data_length

        if kind not in (0x80, 0x90):
            continue

        pitch = values[0]
        velocity = values[1]
        key = (channel, pitch)
        is_on = kind == 0x90 and velocity > 0
        if is_on:
            active[key].append((tick, velocity))
            continue

        if not active[key]:
            warnings.append(
                f"Pista {track_index + 1}: note_off sin note_on para MIDI {pitch} "
                f"en tick {tick}."
            )
            continue
        onset, onset_velocity = active[key].popleft()
        if tick <= onset:
            warnings.append(
                f"Pista {track_index + 1}: nota MIDI {pitch} con duración no positiva omitida."
            )
            continue
        notes.append(
            MidiNote(
                pitch=pitch,
                onset=onset,
                duration=tick - onset,
                track=track_index,
                channel=channel,
                velocity=onset_velocity,
            )
        )

    for (channel, pitch), queue in active.items():
        for onset, _ in queue:
            warnings.append(
                f"Pista {track_index + 1}: note_on sin note_off para MIDI {pitch}, "
                f"canal {channel + 1}, en tick {onset}."
            )
    return notes, warnings


def parse_midi(data: bytes) -> MidiFileData:
    """Extrae notas de un SMF tipo 0 o 1 manteniendo tiempos enteros exactos."""

    if len(data) < 14 or data[:4] != b"MThd":
        raise MidiParseError("El archivo no comienza con una cabecera MIDI MThd")
    header_length = _u32(data, 4)
    if header_length < 6 or 8 + header_length > len(data):
        raise MidiParseError("Cabecera MIDI truncada")
    midi_format = _u16(data, 8)
    track_count = _u16(data, 10)
    division = _u16(data, 12)
    if midi_format not in (0, 1):
        raise MidiParseError("Solo se admiten archivos MIDI de tipo 0 y 1")
    if track_count < 1:
        raise MidiParseError("El MIDI no contiene pistas")
    if division == 0:
        raise MidiParseError("La división temporal MIDI no puede ser cero")

    pos = 8 + header_length
    notes: list[MidiNote] = []
    warnings: list[str] = []
    for track_index in range(track_count):
        if pos + 8 > len(data) or data[pos : pos + 4] != b"MTrk":
            raise MidiParseError(f"No se encontró la pista MIDI {track_index + 1}")
        length = _u32(data, pos + 4)
        start = pos + 8
        end = start + length
        if end > len(data):
            raise MidiParseError(f"La pista MIDI {track_index + 1} está truncada")
        track_notes, track_warnings = _parse_track(data[start:end], track_index)
        notes.extend(track_notes)
        warnings.extend(track_warnings)
        pos = end

    notes.sort(key=lambda n: (n.onset, n.offset, n.pitch, n.track, n.channel))
    return MidiFileData(
        format=midi_format,
        division=division,
        tracks=track_count,
        notes=tuple(notes),
        warnings=tuple(warnings),
    )
