"""Contexto de ocurrencias y comparaciones básicas del Capítulo 3.

Este módulo es deliberadamente independiente de la forma MTI: normaliza los
registros contextuales, construye las representaciones coordinadas y calcula
los bloques melódico, armónico y rítmico-métrico sin modificar D_gamma.
"""

from __future__ import annotations

from functools import lru_cache
from fractions import Fraction
from typing import Any, Iterable

from .compare import ComparisonError, _components, _validated_family, _weights


class ContextError(ValueError):
    pass


PROVENANCE = {"extracted", "annotated", "inferred"}
STATUSES = {"available", "missing"}
START_TYPES = {"thet", "anacr", "aceph"}


def _exact(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _value(value: Fraction) -> dict[str, str | float]:
    return {"exact": _exact(value), "value": float(value)}


def _fraction(raw: Any, field: str, *, positive: bool = False) -> Fraction:
    if isinstance(raw, dict):
        raw = raw.get("exact")
    if type(raw) not in (str, int):
        raise ContextError(f"{field} debe ser un racional exacto")
    text = str(raw)
    try:
        result = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise ContextError(f"{field} no es un racional válido") from exc
    if text != _exact(result):
        raise ContextError(f"{field} debe estar en forma canónica ({_exact(result)})")
    if positive and result <= 0:
        raise ContextError(f"{field} debe ser positivo")
    return result


def _provenance(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("kind") not in PROVENANCE:
        raise ContextError(f"{field}.kind debe ser extracted, annotated o inferred")
    allowed = {"kind", "method", "parameters", "confidence", "source"}
    unknown = set(raw) - allowed
    if unknown:
        raise ContextError(f"Campos de procedencia desconocidos en {field}: {', '.join(sorted(unknown))}")
    if raw["kind"] == "inferred" and not isinstance(raw.get("method"), str):
        raise ContextError(f"{field}.method es obligatorio para procedencia inferred")
    return dict(raw)


def _phase_provenance(raw: Any, field: str) -> dict[str, Any]:
    names = ("source_time", "cycle_origin", "cycle_length", "meter")
    if isinstance(raw, dict) and raw.get("kind") in PROVENANCE:
        shared = _provenance(raw, field)
        return {name: dict(shared) for name in names}
    if not isinstance(raw, dict) or set(raw) != set(names):
        raise ContextError(f"{field} debe declarar la procedencia de source_time, cycle_origin, cycle_length y meter")
    return {name: _provenance(raw[name], f"{field}.{name}") for name in names}


def _descriptor(raw: Any, field: str) -> tuple[int, Fraction, Fraction]:
    if not isinstance(raw, dict) or set(raw) != {"h", "u", "v"} or type(raw.get("h")) is not int:
        raise ContextError(f"{field} debe ser un descriptor estructural (h,u,v)")
    u = _fraction(raw["u"], f"{field}.u")
    v = _fraction(raw["v"], f"{field}.v")
    if not 0 <= u < v <= 1:
        raise ContextError(f"{field} debe satisfacer 0 ≤ u < v ≤ 1")
    return raw["h"], u, v


def _descriptor_json(value: tuple[int, Fraction, Fraction]) -> dict[str, Any]:
    return {"h": value[0], "u": _exact(value[1]), "v": _exact(value[2])}


def _missing_context() -> dict[str, Any]:
    return {
        "schema": "cap3-context-1.0",
        "melodic": {
            "in": {"availability": "missing", "relations": None},
            "out": {"availability": "missing", "relations": None},
        },
        "harmonic": {
            "in": {"availability": "missing", "from": None, "to": None},
            "out": {"availability": "missing", "from": None, "to": None},
        },
        "rhythmic_metric": {
            "phase": {"availability": "missing", "value": None},
            "start": {"availability": "missing", "category": None},
        },
    }


def _normalize_melodic(raw: Any, family: set[tuple[int, Fraction, Fraction]]) -> dict[str, Any]:
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {"in", "out"}:
        raise ContextError("context.melodic debe contener únicamente in y out")
    result: dict[str, Any] = {}
    for direction in ("in", "out"):
        item = raw.get(direction, {"availability": "missing"})
        if not isinstance(item, dict) or item.get("availability") not in STATUSES:
            raise ContextError(f"context.melodic.{direction}.availability debe ser available o missing")
        if item["availability"] == "missing":
            result[direction] = {"availability": "missing", "relations": None}
            continue
        relations = item.get("relations")
        if not isinstance(relations, list):
            raise ContextError(f"context.melodic.{direction}.relations debe ser una lista")
        normalized = []
        for index, relation in enumerate(relations, start=1):
            if not isinstance(relation, dict):
                raise ContextError(f"Relación melódica {direction} {index} no válida")
            anchor = _descriptor(relation.get("anchor"), f"context.melodic.{direction}.relations[{index}].anchor")
            if anchor not in family:
                raise ContextError(f"La relación melódica {direction} {index} apunta a un evento inexistente")
            interval = relation.get("interval")
            if type(interval) is not int:
                raise ContextError(f"El intervalo melódico {direction} {index} debe ser entero y dirigido")
            normalized.append({
                "id": relation.get("id") or f"mel-{direction}-{index}",
                "anchor": _descriptor_json(anchor),
                "interval": interval,
                "provenance": _provenance(relation.get("provenance"), f"context.melodic.{direction}.relations[{index}].provenance"),
                **({"base_event_id": relation["base_event_id"]} if isinstance(relation.get("base_event_id"), str) else {}),
                **({"continuity": relation["continuity"]} if "continuity" in relation else {}),
            })
        result[direction] = {"availability": "available", "relations": normalized}
    return result


def _normalize_state(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContextError(f"{field} debe ser un estado acordal")
    root = raw.get("root")
    bass_pc = raw.get("bass_pc")
    intervals = raw.get("intervals")
    if type(root) is not int or not 0 <= root < 12:
        raise ContextError(f"{field}.root debe pertenecer a Z12")
    if type(bass_pc) is not int or not 0 <= bass_pc < 12:
        raise ContextError(f"{field}.bass_pc debe pertenecer a Z12")
    if not isinstance(intervals, list) or any(type(value) is not int or not 0 <= value < 12 for value in intervals):
        raise ContextError(f"{field}.intervals debe ser una lista de clases interválicas en Z12")
    bass_pitch = raw.get("bass_pitch")
    if bass_pitch is not None and type(bass_pitch) is not int:
        raise ContextError(f"{field}.bass_pitch debe ser entero o null")
    compatible = bass_pitch is None or (bass_pitch - root) % 12 == bass_pc
    return {
        "root": root,
        "intervals": sorted(set(intervals)),
        "bass_pc": bass_pc,
        "bass_pitch": bass_pitch,
        "compatibility": "ok" if compatible else "incompatible",
        "provenance": _provenance(raw.get("provenance"), f"{field}.provenance"),
    }


def _normalize_harmonic(raw: Any) -> dict[str, Any]:
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {"in", "out"}:
        raise ContextError("context.harmonic debe contener únicamente in y out")
    result: dict[str, Any] = {}
    for direction in ("in", "out"):
        item = raw.get(direction, {"availability": "missing"})
        if not isinstance(item, dict) or item.get("availability") not in STATUSES:
            raise ContextError(f"context.harmonic.{direction}.availability debe ser available o missing")
        if item["availability"] == "missing":
            result[direction] = {"availability": "missing", "from": None, "to": None}
            continue
        result[direction] = {
            "availability": "available",
            "from": _normalize_state(item.get("from"), f"context.harmonic.{direction}.from"),
            "to": _normalize_state(item.get("to"), f"context.harmonic.{direction}.to"),
        }
    return result


def _normalize_meter(raw: Any, field: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"numerator", "denominator", "grouping"}:
        raise ContextError(f"{field} debe contener numerator, denominator y grouping")
    n, d, grouping = raw["numerator"], raw["denominator"], raw["grouping"]
    if type(n) is not int or n <= 0 or type(d) is not int or d <= 0:
        raise ContextError(f"{field} requiere numerador y denominador positivos")
    if grouping is not None:
        if not isinstance(grouping, list) or not grouping or any(type(x) is not int or x <= 0 for x in grouping) or sum(grouping) != n:
            raise ContextError(f"{field}.grouping debe ser null o una partición positiva del numerador")
    return {"numerator": n, "denominator": d, "grouping": grouping}


def _normalize_rhythm(raw: Any) -> dict[str, Any]:
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {"phase", "start"}:
        raise ContextError("context.rhythmic_metric debe contener únicamente phase y start")
    phase = raw.get("phase", {"availability": "missing"})
    if not isinstance(phase, dict) or phase.get("availability") not in STATUSES:
        raise ContextError("context.rhythmic_metric.phase.availability debe ser available o missing")
    if phase["availability"] == "missing":
        normalized_phase = {"availability": "missing", "value": None}
    else:
        t0 = _fraction(phase.get("source_time"), "context.rhythmic_metric.phase.source_time")
        origin = _fraction(phase.get("cycle_origin"), "context.rhythmic_metric.phase.cycle_origin")
        length = _fraction(phase.get("cycle_length"), "context.rhythmic_metric.phase.cycle_length", positive=True)
        if not origin <= t0 < origin + length:
            raise ContextError("La entrada métrica debe satisfacer b ≤ t0 < b + L")
        meter = _normalize_meter(phase.get("meter"), "context.rhythmic_metric.phase.meter")
        normalized_phase = {
            "availability": "available",
            "source_time": _exact(t0),
            "cycle_origin": _exact(origin),
            "cycle_length": _exact(length),
            "meter": meter,
            "value": _value((t0 - origin) / length),
            "derivation": "(source_time-cycle_origin)/cycle_length",
            "provenance": _phase_provenance(phase.get("provenance"), "context.rhythmic_metric.phase.provenance"),
        }
    start = raw.get("start", {"availability": "missing"})
    if not isinstance(start, dict) or start.get("availability") not in STATUSES:
        raise ContextError("context.rhythmic_metric.start.availability debe ser available o missing")
    if start["availability"] == "missing":
        normalized_start = {"availability": "missing", "category": None}
    else:
        if start.get("category") not in START_TYPES:
            raise ContextError("context.rhythmic_metric.start.category debe ser thet, anacr o aceph")
        normalized_start = {
            "availability": "available",
            "category": start["category"],
            "provenance": _provenance(start.get("provenance"), "context.rhythmic_metric.start.provenance"),
        }
    return {"phase": normalized_phase, "start": normalized_start}


def normalize_context(raw: Any, family: list[dict[str, Any]]) -> dict[str, Any]:
    if raw is None:
        return _missing_context()
    if not isinstance(raw, dict):
        raise ContextError("context debe ser un objeto")
    unknown = set(raw) - {"schema", "melodic", "harmonic", "rhythmic_metric"}
    if unknown:
        raise ContextError(f"Dimensiones contextuales desconocidas: {', '.join(sorted(unknown))}")
    if raw.get("schema", "cap3-context-1.0") != "cap3-context-1.0":
        raise ContextError("Solo se admite el esquema contextual cap3-context-1.0")
    validated = {descriptor for descriptor, _ in _validated_family(family, "contexto")}
    return {
        "schema": "cap3-context-1.0",
        "melodic": _normalize_melodic(raw.get("melodic"), validated),
        "harmonic": _normalize_harmonic(raw.get("harmonic")),
        "rhythmic_metric": _normalize_rhythm(raw.get("rhythmic_metric")),
    }


def _base_from_graph(graph: dict[str, Any], base_events: list[dict[str, Any]] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    sync = [
        {"id": f"base-{node['id']}", "kind": "sync", "index": node["index"], "source": annotation}
        for node, annotation in zip(graph["nodes"]["sync"], graph["source_annotations"].get("sync", []))
    ]
    if not sync:
        sync = [{"id": f"base-{node['id']}", "kind": "sync", "index": node["index"]} for node in graph["nodes"]["sync"]]
    source_events = base_events
    if source_events is None:
        source_events = [
            {
                "id": f"base-event-{event['index']}",
                "pitch": None,
                "h": event["relative_pitch"],
                "u": event["onset_normalized"]["exact"],
                "v": event["offset_normalized"]["exact"],
            }
            for event in graph["nodes"]["events"]
        ]
    structural_by_descriptor = {
        (item["h"], item["u"]["exact"], item["v"]["exact"]): f"event-{index}"
        for index, item in enumerate(graph["normalized_family"], start=1)
    }
    event_nodes, event_trace = [], []
    for index, item in enumerate(source_events, start=1):
        identifier = item.get("id") or f"base-event-{index}"
        event_nodes.append({"id": identifier, "kind": "event", **{key: value for key, value in item.items() if key != "id"}})
        key = (item["h"], str(item["u"]), str(item["v"]))
        event_trace.append({"base": identifier, "structural": structural_by_descriptor[key]})
    sync_trace = [{"base": node["id"], "structural": f"theta-{node['index']}"} for node in sync]
    normalized_to_sync = {node["normalized"]["exact"]: f"base-{node['id']}" for node in graph["nodes"]["sync"]}
    base_edges = [
        {"id": f"base-temporal-{index}", "type": "temporal", "source": sync[index]["id"], "target": sync[index + 1]["id"]}
        for index in range(max(0, len(sync) - 1))
    ]
    for node in event_nodes:
        base_edges.extend([
            {"id": f"base-onset-{node['id']}", "type": "onset", "source": normalized_to_sync[str(node["u"])], "target": node["id"]},
            {"id": f"base-offset-{node['id']}", "type": "offset", "source": node["id"], "target": normalized_to_sync[str(node["v"])]},
        ])
    base = {"nodes": {"sync": sync, "events": event_nodes}, "edges": base_edges}
    return base, {"sync": sync_trace, "events": event_trace}


def attach_context(graph: dict[str, Any], raw_context: Any = None, *, base_events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    context = normalize_context(raw_context, graph["normalized_family"])
    base, traceability = _base_from_graph(graph, base_events)
    context_nodes: list[dict[str, Any]] = []
    context_edges: list[dict[str, Any]] = []
    views = {"melodic": {"nodes": [], "edges": []}, "harmonic": {"nodes": [], "edges": []}, "rhythmic_metric": {"nodes": [], "edges": []}}
    descriptor_to_structural = {
        (item["h"], item["u"]["exact"], item["v"]["exact"]): f"event-{index}"
        for index, item in enumerate(graph["normalized_family"], start=1)
    }
    base_by_structural: dict[str, list[str]] = {}
    for item in traceability["events"]:
        base_by_structural.setdefault(item["structural"], []).append(item["base"])
    for direction in ("in", "out"):
        melodic = context["melodic"][direction]
        if melodic["availability"] == "available":
            for relation in melodic["relations"]:
                external_id = f"ctx-{relation['id']}"
                anchor = relation["anchor"]
                structural_anchor = descriptor_to_structural[(anchor["h"], anchor["u"], anchor["v"])]
                candidates = base_by_structural[structural_anchor]
                anchor_id = relation.get("base_event_id")
                if anchor_id is None and len(candidates) == 1:
                    anchor_id = candidates[0]
                if anchor_id not in candidates:
                    raise ContextError(f"La relación {relation['id']} requiere un base_event_id válido para su anclaje en G0")
                context_nodes.append({"id": external_id, "kind": "external_melodic_event", "dimension": "melodic"})
                edge = {"id": relation["id"], "type": f"melodic_{direction}", "source": external_id if direction == "in" else anchor_id, "target": anchor_id if direction == "in" else external_id, "structural_anchor": structural_anchor, "interval": relation["interval"], "provenance": relation["provenance"]}
                context_edges.append(edge)
                views["melodic"]["nodes"].extend([external_id, anchor_id])
                views["melodic"]["edges"].append(edge["id"])
        harmonic = context["harmonic"][direction]
        if harmonic["availability"] == "available":
            left_id, right_id = f"ctx-harm-{direction}-from", f"ctx-harm-{direction}-to"
            context_nodes.extend([
                {"id": left_id, "kind": "harmonic_state", "dimension": "harmonic", "state": harmonic["from"]},
                {"id": right_id, "kind": "harmonic_state", "dimension": "harmonic", "state": harmonic["to"]},
            ])
            edge = {"id": f"harm-{direction}", "type": f"harmonic_{direction}", "source": left_id, "target": right_id}
            boundary_id = "base-theta-0" if direction == "in" else f"base-theta-{len(graph['nodes']['sync']) - 1}"
            anchor_edge = {"id": f"harm-{direction}-anchor", "type": "harmonic_boundary_anchor", "source": right_id if direction == "in" else boundary_id, "target": boundary_id if direction == "in" else left_id}
            context_edges.extend([edge, anchor_edge])
            views["harmonic"]["nodes"].extend([left_id, right_id, boundary_id])
            views["harmonic"]["edges"].extend([edge["id"], anchor_edge["id"]])
    if context["rhythmic_metric"]["phase"]["availability"] == "available":
        node = {"id": "ctx-meter", "kind": "metric_reference", "dimension": "rhythmic_metric", "phase": context["rhythmic_metric"]["phase"]}
        context_nodes.append(node)
        edge = {"id": "metric-entry", "type": "metric_phase", "source": "ctx-meter", "target": "base-theta-0"}
        context_edges.append(edge)
        views["rhythmic_metric"] = {"nodes": ["ctx-meter", "base-theta-0"], "edges": ["metric-entry"]}
    graph["context"] = context
    graph["representations"] = {
        "base": base,
        "structural": {"profile": graph["profile"], "nodes": graph["nodes"], "edges": graph["edges"]},
        "extended": {"base_embedded": True, "base": base, "context_nodes": context_nodes, "context_edges": context_edges},
        "views": views,
        "traceability": traceability,
    }
    return graph


def _optimal_correspondences(family_a: list[dict[str, Any]], family_b: list[dict[str, Any]], parameters: dict[str, Any] | None) -> list[dict[str, Any]]:
    weights = _weights(parameters)
    indexed_a = _validated_family(family_a, "A")
    indexed_b = _validated_family(family_b, "B")
    a = [descriptor for descriptor, _ in indexed_a]
    b = [descriptor for descriptor, _ in indexed_b]
    pair_costs = [[_components(left, right, weights)["total"] for right in b] for left in a]
    gamma = weights["gamma"]

    @lru_cache(maxsize=None)
    def solve(index: int, used: int) -> tuple[Fraction, tuple[tuple[tuple[int, int], ...], ...]]:
        if index == len(a):
            return gamma * (len(b) - used.bit_count()), ((),)
        options: list[tuple[Fraction, tuple[tuple[tuple[int, int], ...], ...]]] = []
        deletion_cost, deletion_paths = solve(index + 1, used)
        options.append((gamma + deletion_cost, deletion_paths))
        for column in range(len(b)):
            if used & (1 << column):
                continue
            suffix_cost, suffix_paths = solve(index + 1, used | (1 << column))
            options.append((pair_costs[index][column] + suffix_cost, tuple((((index, column),) + path) for path in suffix_paths)))
        best = min(cost for cost, _ in options)
        paths = tuple(sorted({path for cost, group in options if cost == best for path in group}))
        return best, paths

    _, paths = solve(0, 0)
    results = []
    for number, path in enumerate(paths, start=1):
        results.append({
            "id": f"structural-correspondence-{number}",
            "pairs": [
                {"event_a": indexed_a[i][1], "event_b": indexed_b[j][1], "descriptor_a": _descriptor_json(a[i]), "descriptor_b": _descriptor_json(b[j])}
                for i, j in path
            ],
        })
    return results


def _assignment_cost(left: list[int], right: list[int], omega: Fraction, gamma: Fraction) -> Fraction:
    @lru_cache(maxsize=None)
    def solve(index: int, used: int) -> Fraction:
        if index == len(left):
            return gamma * (len(right) - used.bit_count())
        best = gamma + solve(index + 1, used)
        for column, value in enumerate(right):
            if not used & (1 << column):
                best = min(best, omega * Fraction(abs(left[index] - value), 12) + solve(index + 1, used | (1 << column)))
        return best
    return solve(0, 0)


def _melodic_direction(left: dict[str, Any], right: dict[str, Any], correspondences: list[dict[str, Any]], omega: Fraction, gamma: Fraction) -> dict[str, Any]:
    if left["availability"] == "missing" or right["availability"] == "missing":
        return {"status": "missing", "results": None}
    total_relations = len(left["relations"]) + len(right["relations"])
    results = []
    for correspondence in correspondences:
        pairs = {
            ((pair["descriptor_a"]["h"], pair["descriptor_a"]["u"], pair["descriptor_a"]["v"]), (pair["descriptor_b"]["h"], pair["descriptor_b"]["u"], pair["descriptor_b"]["v"]))
            for pair in correspondence["pairs"]
        }
        anchors_a = {first for first, _ in pairs}
        anchors_b = {second for _, second in pairs}
        covered_a = [relation for relation in left["relations"] if (relation["anchor"]["h"], relation["anchor"]["u"], relation["anchor"]["v"]) in anchors_a]
        covered_b = [relation for relation in right["relations"] if (relation["anchor"]["h"], relation["anchor"]["u"], relation["anchor"]["v"]) in anchors_b]
        coverage = Fraction(len(covered_a) + len(covered_b), total_relations) if total_relations else Fraction(1)
        if total_relations and coverage == 0:
            continue
        cost = Fraction(0)
        for anchor_a, anchor_b in pairs:
            intervals_a = [item["interval"] for item in covered_a if (item["anchor"]["h"], item["anchor"]["u"], item["anchor"]["v"]) == anchor_a]
            intervals_b = [item["interval"] for item in covered_b if (item["anchor"]["h"], item["anchor"]["u"], item["anchor"]["v"]) == anchor_b]
            cost += _assignment_cost(intervals_a, intervals_b, omega, gamma)
        results.append({"dissimilarity": _value(cost), "coverage": _value(coverage), "structural_correspondence_id": correspondence["id"]})
    if not results:
        return {"status": "incompatible", "results": None}
    unique = []
    seen = set()
    for item in results:
        key = (item["dissimilarity"]["exact"], item["coverage"]["exact"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
        else:
            existing = next(value for value in unique if (value["dissimilarity"]["exact"], value["coverage"]["exact"]) == key)
            existing.setdefault("equivalent_correspondence_ids", []).append(item["structural_correspondence_id"])
    return {"status": "ok", "results": unique}


def _transition(item: dict[str, Any]) -> dict[str, Any] | None:
    if item["availability"] == "missing":
        return None
    first, second = item["from"], item["to"]
    incompatible = first["compatibility"] == "incompatible" or second["compatibility"] == "incompatible"
    return {
        "root": (second["root"] - first["root"]) % 12,
        "inversion": (first["bass_pc"], second["bass_pc"]),
        "bass_motion": None if first["bass_pitch"] is None or second["bass_pitch"] is None else second["bass_pitch"] - first["bass_pitch"],
        "interval_constitution": (set(first["intervals"]), set(second["intervals"])),
        "bass_status": "incompatible" if incompatible else "available" if first["bass_pitch"] is not None and second["bass_pitch"] is not None else "missing",
        "inversion_status": "incompatible" if incompatible else "available",
    }


def _circ(left: int, right: int) -> int:
    delta = abs(left - right)
    return min(delta, 12 - delta)


def _jaccard(left: set[int], right: set[int]) -> Fraction:
    union = left | right
    return Fraction(0) if not union else 1 - Fraction(len(left & right), len(union))


def _component(value: Fraction | int | None, status: str) -> dict[str, Any]:
    return {"value": _value(Fraction(value)) if status == "ok" and value is not None else None, "status": status}


def _harmonic_direction(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    first, second = _transition(left), _transition(right)
    if first is None or second is None:
        return {name: _component(None, "missing") for name in ("root", "inversion", "bass_motion", "interval_constitution")}
    root = _component(_circ(first["root"], second["root"]), "ok")
    inversion_status = "incompatible" if "incompatible" in (first["inversion_status"], second["inversion_status"]) else "ok"
    inversion = _component(Fraction(_circ(first["inversion"][0], second["inversion"][0]) + _circ(first["inversion"][1], second["inversion"][1]), 2), inversion_status)
    if "incompatible" in (first["bass_status"], second["bass_status"]):
        bass = _component(None, "incompatible")
    elif "missing" in (first["bass_status"], second["bass_status"]):
        bass = _component(None, "missing")
    else:
        bass = _component(abs(first["bass_motion"] - second["bass_motion"]), "ok")
    constitution = _component(Fraction(_jaccard(first["interval_constitution"][0], second["interval_constitution"][0]) + _jaccard(first["interval_constitution"][1], second["interval_constitution"][1]), 2), "ok")
    return {"root": root, "inversion": inversion, "bass_motion": bass, "interval_constitution": constitution}


def _rhythm(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_phase, right_phase = left["phase"], right["phase"]
    if left_phase["availability"] == "missing" or right_phase["availability"] == "missing":
        phase = _component(None, "missing")
    elif left_phase["meter"] != right_phase["meter"]:
        phase = _component(None, "incompatible")
    else:
        a, b = Fraction(left_phase["value"]["exact"]), Fraction(right_phase["value"]["exact"])
        delta = abs(a - b)
        phase = _component(2 * min(delta, 1 - delta), "ok")
    left_start, right_start = left["start"], right["start"]
    start = _component(None, "missing") if left_start["availability"] == "missing" or right_start["availability"] == "missing" else _component(int(left_start["category"] != right_start["category"]), "ok")
    return {"phase": phase, "start": start}


def compare_contexts(
    family_a: list[dict[str, Any]],
    family_b: list[dict[str, Any]],
    context_a: Any,
    context_b: Any,
    parameters: dict[str, Any] | None = None,
    contextual_parameters: dict[str, Any] | None = None,
    structural_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    left = normalize_context(context_a, family_a)
    right = normalize_context(context_b, family_b)
    params = contextual_parameters or {}
    unknown = set(params) - {"omega_interval", "gamma_mel_in", "gamma_mel_out"}
    if unknown:
        raise ContextError(f"Parámetros contextuales desconocidos: {', '.join(sorted(unknown))}")
    omega = _fraction(params.get("omega_interval", "1"), "omega_interval", positive=True)
    gamma_in = _fraction(params.get("gamma_mel_in", "1"), "gamma_mel_in", positive=True)
    gamma_out = _fraction(params.get("gamma_mel_out", "1"), "gamma_mel_out", positive=True)
    melodic_comparable = any(
        left["melodic"][direction]["availability"] == "available"
        and right["melodic"][direction]["availability"] == "available"
        for direction in ("in", "out")
    )
    if structural_comparison is not None:
        correspondences = [{
            "id": "structural-correspondence-1",
            "pairs": [
                {
                    "event_a": item["event_a"],
                    "event_b": item["event_b"],
                    "descriptor_a": {
                        "h": item["descriptor_a"]["h"],
                        "u": item["descriptor_a"]["u"]["exact"],
                        "v": item["descriptor_a"]["v"]["exact"],
                    },
                    "descriptor_b": {
                        "h": item["descriptor_b"]["h"],
                        "u": item["descriptor_b"]["u"]["exact"],
                        "v": item["descriptor_b"]["v"]["exact"],
                    },
                }
                for item in structural_comparison.get("matches", [])
            ],
        }]
    elif not melodic_comparable:
        correspondences = []
    else:
        correspondences = _optimal_correspondences(family_a, family_b, parameters)
    return {
        "melodic": {
            "in": _melodic_direction(left["melodic"]["in"], right["melodic"]["in"], correspondences, omega, gamma_in),
            "out": _melodic_direction(left["melodic"]["out"], right["melodic"]["out"], correspondences, omega, gamma_out),
            "parameters": {"omega_interval": _value(omega), "gamma_in": _value(gamma_in), "gamma_out": _value(gamma_out)},
        },
        "harmonic": {
            "in": _harmonic_direction(left["harmonic"]["in"], right["harmonic"]["in"]),
            "out": _harmonic_direction(left["harmonic"]["out"], right["harmonic"]["out"]),
        },
        "rhythmic_metric": _rhythm(left["rhythmic_metric"], right["rhythmic_metric"]),
        "records": {"a": left, "b": right},
        "structural_correspondences": correspondences,
        "aggregation": None,
    }
