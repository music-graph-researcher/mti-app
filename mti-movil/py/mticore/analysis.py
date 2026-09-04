"""Descriptores derivados de la forma representada por un grafo MTI."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Any


def _fraction(value: Fraction) -> dict[str, str | float]:
    return {
        "exact": str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}",
        "value": float(value),
    }


def _as_fraction(payload: dict[str, Any]) -> Fraction:
    return Fraction(str(payload["exact"]))


def derive_form_analysis(syncs: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Resume actividad, registro, contorno y relaciones sin añadir otra invariancia."""

    activity = []
    silence = Fraction(0)
    weighted_polyphony = Fraction(0)
    for left, right in zip(syncs, syncs[1:]):
        start = left["index"]
        active = [
            event["index"]
            for event in events
            if event["onset_index"] <= start < event["offset_index"]
        ]
        duration = _as_fraction(right["normalized"]) - _as_fraction(left["normalized"])
        weighted_polyphony += len(active) * duration
        if not active:
            silence += duration
        activity.append(
            {
                "start_sync": start,
                "end_sync": right["index"],
                "start": left["normalized"],
                "end": right["normalized"],
                "duration": _fraction(duration),
                "active_events": active,
                "count": len(active),
                "is_silence": not active,
            }
        )

    heights = [event["relative_pitch"] for event in events]
    onset_groups: dict[int, list[int]] = {}
    for event in events:
        onset_groups.setdefault(event["onset_index"], []).append(event["relative_pitch"])
    attack_profile = []
    previous: Fraction | None = None
    contour_steps = []
    for onset_index, group in sorted(onset_groups.items()):
        centroid = Fraction(sum(group), len(group))
        direction = None
        interval = None
        if previous is not None:
            delta = centroid - previous
            direction = "up" if delta > 0 else "down" if delta < 0 else "same"
            interval = _fraction(delta)
            contour_steps.append(direction)
        attack_profile.append(
            {
                "sync_index": onset_index,
                "event_count": len(group),
                "centroid_h": _fraction(centroid),
                "direction_from_previous": direction,
                "interval_from_previous": interval,
            }
        )
        previous = centroid

    relations = []
    relation_counts: Counter[str] = Counter()
    for position, first in enumerate(events):
        for second in events[position + 1 :]:
            labels = []
            if first["onset_index"] == second["onset_index"]:
                labels.append("simultaneous_onset")
            if first["offset_index"] == second["offset_index"]:
                labels.append("simultaneous_offset")
            if (
                first["onset_index"] == second["onset_index"]
                and first["offset_index"] == second["offset_index"]
            ):
                labels.append("parallel_span")

            if first["onset_index"] <= second["onset_index"] and second["offset_index"] <= first["offset_index"] and not (
                first["onset_index"] == second["onset_index"] and first["offset_index"] == second["offset_index"]
            ):
                labels.append("first_contains_second")
            elif second["onset_index"] <= first["onset_index"] and first["offset_index"] <= second["offset_index"]:
                labels.append("second_contains_first")
            elif max(first["onset_index"], second["onset_index"]) < min(first["offset_index"], second["offset_index"]):
                labels.append("overlap")
            elif first["offset_index"] == second["onset_index"] or second["offset_index"] == first["onset_index"]:
                labels.append("touching_succession")
            else:
                labels.append("separated")

            for label in labels:
                relation_counts[label] += 1
            relations.append({"event_a": first["index"], "event_b": second["index"], "relations": labels})

    duration_counts = Counter(event["duration_normalized"]["exact"] for event in events)
    repeated_durations = [
        {"duration": duration, "count": count}
        for duration, count in sorted(duration_counts.items(), key=lambda item: Fraction(item[0]))
        if count > 1
    ]
    thirds = []
    for region in range(3):
        lower, upper = Fraction(region, 3), Fraction(region + 1, 3)
        attacks = sum(
            1
            for event in events
            if lower <= _as_fraction(event["onset_normalized"]) < upper or (region == 2 and _as_fraction(event["onset_normalized"]) == 1)
        )
        thirds.append({"region": region + 1, "attacks": attacks})

    mean_height = Fraction(sum(heights), len(heights))
    return {
        "temporal": {
            "activity_segments": activity,
            "silence_ratio": _fraction(silence),
            "sounding_ratio": _fraction(1 - silence),
            "max_polyphony": max((segment["count"] for segment in activity), default=0),
            "mean_polyphony": _fraction(weighted_polyphony),
            "attack_distribution_thirds": thirds,
            "repeated_durations": repeated_durations,
            "boundary_events": {
                "opening": [event["index"] for event in events if event["onset_index"] == 0],
                "closing": [event["index"] for event in events if event["offset_index"] == syncs[-1]["index"]],
            },
        },
        "pitch": {
            "minimum_h": min(heights),
            "maximum_h": max(heights),
            "range": max(heights) - min(heights),
            "mean_h": _fraction(mean_height),
            "relative_pitch_classes": sorted({height % 12 for height in heights}),
            "attack_centroid_profile": attack_profile,
            "contour_steps": contour_steps,
        },
        "relations": {
            "pairs": relations,
            "counts": dict(sorted(relation_counts.items())),
        },
    }
