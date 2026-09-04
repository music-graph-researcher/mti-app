"""Cálculo operacional exacto del capítulo 5.

El módulo mantiene separados el coste de una trayectoria concreta y la
distancia estática D_gamma. Todas las coordenadas y costes se calculan con
``Fraction``; los decimales sólo aparecen como ayudas de presentación.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import heapq
import itertools
import math
import time
from typing import Any, Iterable

from .compare import ComparisonError, _components, _weights, compare_families
from . import ai_summaries


Event = tuple[int, Fraction, Fraction]
State = frozenset[Event]
KINDS = {"h", "u", "v", "ins", "del", "id"}


class OperationalError(ValueError):
    """Entrada o acción fuera del dominio operacional."""


def operational_weights(parameters: dict[str, Any] | None) -> dict[str, Fraction]:
    """Perfil de §5.8: los cinco parámetros son estrictamente positivos."""
    weights = _weights(parameters)
    non_positive = [name for name, value in weights.items() if value <= 0]
    if non_positive:
        raise OperationalError(f"El perfil operacional exige pesos positivos: {', '.join(non_positive)}")
    return weights


def _exact(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def rational_payload(value: Fraction) -> dict[str, str | float]:
    return {"exact": _exact(value), "value": float(value)}


def _fraction(value: Any, name: str) -> Fraction:
    if isinstance(value, dict):
        value = value.get("exact")
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        raise OperationalError(f"{name} debe ser un entero o una fracción exacta escrita como texto")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise OperationalError(f"{name} no es una fracción válida") from exc
    return result


def _event(value: Any, name: str = "descriptor") -> Event:
    if isinstance(value, dict):
        if set(value) != {"h", "u", "v"}:
            raise OperationalError(f"{name} debe contener exactamente h, u y v")
        raw = (value["h"], value["u"], value["v"])
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        raw = value
    else:
        raise OperationalError(f"{name} debe ser [h, u, v]")
    if type(raw[0]) is not int:
        raise OperationalError(f"La altura de {name} debe ser un entero")
    return raw[0], _fraction(raw[1], f"u de {name}"), _fraction(raw[2], f"v de {name}")


def validate_state(events: Iterable[Event], name: str = "estado") -> State:
    listed = list(events)
    if not listed:
        raise OperationalError(f"El {name} no puede estar vacío")
    if len(set(listed)) != len(listed):
        raise OperationalError(f"El {name} contiene descriptores duplicados")
    for _, u, v in listed:
        if not 0 <= u < v <= 1:
            raise OperationalError(f"El {name} debe satisfacer 0 ≤ u < v ≤ 1")
    if min(u for _, u, _ in listed) != 0 or max(v for _, _, v in listed) != 1:
        raise OperationalError(f"El {name} debe tener soporte temporal exacto [0,1]")
    return frozenset(listed)


def parse_state(value: Any, name: str = "estado") -> State:
    if isinstance(value, dict):
        value = value.get("events", value.get("normalized_family"))
    if not isinstance(value, list):
        raise OperationalError(f"El {name} debe contener una lista events")
    return validate_state((_event(item, f"{name}[{index}]") for index, item in enumerate(value, 1)), name)


def event_payload(event: Event) -> dict[str, Any]:
    h, u, v = event
    return {"h": h, "u": rational_payload(u), "v": rational_payload(v)}


def state_payload(state: State) -> dict[str, Any]:
    ordered = sorted(state)
    return {
        "events": [[h, _exact(u), _exact(v)] for h, u, v in ordered],
        "descriptors": [event_payload(event) for event in ordered],
        "cardinality": len(ordered),
        "support": ["0", "1"],
    }


def _state_key(state: State) -> tuple[Event, ...]:
    return tuple(sorted(state))


def state_id(state: State) -> str:
    def _u(x: Fraction) -> str:
        return f"{x.numerator}/{x.denominator}" if x.denominator != 1 else f"{x.numerator}/1"
    material = ";".join(f"{h},{_u(Fraction(u))},{_u(Fraction(v))}" for h, u, v in sorted(state))
    return "q-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Action:
    kind: str
    event: Event | None = None
    delta: int | Fraction | None = None


def parse_action(value: Any) -> Action:
    if not isinstance(value, dict):
        raise OperationalError("La acción debe ser un objeto")
    kind = value.get("kind")
    if kind not in KINDS:
        raise OperationalError("kind debe ser h, u, v, ins, del o id")
    if kind == "id":
        return Action(kind)
    event = _event(value.get("event"), "event")
    if kind in {"ins", "del"}:
        return Action(kind, event)
    raw_delta = value.get("delta")
    if kind == "h":
        if type(raw_delta) is not int:
            raise OperationalError("El desplazamiento de altura debe ser entero")
        delta: int | Fraction = raw_delta
    else:
        delta = _fraction(raw_delta, "delta")
    return Action(kind, event, delta)


def action_payload(action: Action) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": action.kind}
    if action.event is not None:
        result["event"] = event_payload(action.event)
    if action.delta is not None:
        result["delta"] = action.delta if isinstance(action.delta, int) else _exact(action.delta)
    return result


def normalize_provisional(events: Iterable[Event]) -> tuple[State, dict[str, Any]]:
    provisional = list(events)
    if not provisional:
        raise OperationalError("La normalización afín no está definida para el conjunto vacío")
    for _, start, end in provisional:
        if start >= end:
            raise OperationalError("Todo descriptor provisional debe satisfacer inicio < fin")
    a = min(start for _, start, _ in provisional)
    b = max(end for _, _, end in provisional)
    if a >= b:
        raise OperationalError("El soporte temporal provisional debe tener longitud positiva")
    support_length = b - a
    scale = 1 / support_length
    mapped = [(h, (start - a) * scale, (end - a) * scale) for h, start, end in provisional]
    if len(set(mapped)) != len(mapped):
        raise OperationalError("La normalización produciría descriptores duplicados")
    state = validate_state(mapped, "estado normalizado")
    report = {
        "a": rational_payload(a),
        "b": rational_payload(b),
        "scale": rational_payload(scale),
        "support_length": rational_payload(support_length),
        "effective": a != 0 or b != 1,
        "descriptor_map": [
            {"from": event_payload(source), "to": event_payload(target)}
            for source, target in zip(sorted(provisional), sorted(mapped))
        ],
    }
    return state, report


def _map_by_support(event: Event, report: dict[str, Any]) -> Event:
    h, u, v = event
    a = Fraction(str(report["a"]["exact"]))
    scale = Fraction(str(report["scale"]["exact"]))
    return h, (u - a) * scale, (v - a) * scale


def _chi_ext(event: Event, weights: dict[str, Fraction]) -> Fraction:
    _, u, v = event
    return weights["omega_on"] * max(-u, 0) + weights["omega_off"] * max(v - 1, 0)


def _transition_rejected(state: State, action: Action, reason: str) -> dict[str, Any]:
    return {
        "admissible": False,
        "reason": reason,
        "rejection_reason": reason,
        "pre_state": state_payload(state),
        "before": state_payload(state),
        "after": None,
        "action": action_payload(action),
        "effective": False,
        "cost": None,
    }


def apply_action(state: State, action: Action, parameters: dict[str, Any] | None = None) -> tuple[State, Fraction, dict[str, Any]]:
    state = validate_state(state)
    weights = operational_weights(parameters)
    if action.kind == "id":
        state_data = state_payload(state)
        return state, Fraction(0), {
            "admissible": True, "pre_state": state_data, "before": state_data, "provisional_state": state_data,
            "post_state": state_data, "after": state_data, "action": action_payload(action), "cost": rational_payload(Fraction(0)),
            "normalization": None, "effective": False, "canonically_inert": True,
        }
    assert action.event is not None
    if action.kind != "ins" and action.event not in state:
        raise OperationalError("El descriptor seleccionado no pertenece al estado")
    if action.kind == "ins" and action.event in state:
        raise OperationalError("El descriptor que se desea insertar ya existe")

    provisional: list[Event]
    normalization: dict[str, Any] | None = None
    if action.kind == "h":
        assert isinstance(action.delta, int)
        h, u, v = action.event
        changed = (h + action.delta, u, v)
        provisional = [changed if x == action.event else x for x in state]
        if len(set(provisional)) != len(provisional):
            raise OperationalError("La acción de altura colapsaría dos descriptores")
        post = validate_state(provisional)
        cost = _components(action.event, changed, weights)["height"]
    elif action.kind in {"u", "v"}:
        assert isinstance(action.delta, Fraction)
        h, u, v = action.event
        changed = (h, u + action.delta, v) if action.kind == "u" else (h, u, v + action.delta)
        if changed[1] >= changed[2]:
            raise OperationalError("El desplazamiento temporal viola inicio < fin")
        provisional = [changed if x == action.event else x for x in state]
        post, normalization = normalize_provisional(provisional)
        cost = weights["omega_on" if action.kind == "u" else "omega_off"] * abs(action.delta)
    elif action.kind == "ins":
        h, u, v = action.event
        if u >= v:
            raise OperationalError("La inserción debe satisfacer inicio < fin")
        provisional = [*state, action.event]
        post, normalization = normalize_provisional(provisional)
        cost = weights["gamma"] + _chi_ext(action.event, weights)
    else:
        if len(state) == 1:
            raise OperationalError("No se puede eliminar el último descriptor")
        provisional = [x for x in state if x != action.event]
        post, normalization = normalize_provisional(provisional)
        removed_in_new_frame = _map_by_support(action.event, normalization)
        cost = weights["gamma"] + _chi_ext(removed_in_new_frame, weights)

    expected_cardinality = len(state) + (1 if action.kind == "ins" else -1 if action.kind == "del" else 0)
    if len(post) != expected_cardinality or cost < 0:
        raise AssertionError("La transición viola cardinalidad o no negatividad del coste")
    before_data, after_data = state_payload(state), state_payload(post)
    record = {
        "admissible": True,
        "pre_state": before_data,
        "before": before_data,
        "provisional_state": {
            "events": [[h, _exact(u), _exact(v)] for h, u, v in sorted(provisional)],
            "cardinality": len(provisional),
        },
        "post_state": after_data,
        "after": after_data,
        "action": action_payload(action),
        "cost": rational_payload(cost),
        "normalization": normalization,
        "effective": post != state,
        "canonically_inert": normalization is None or not normalization["effective"],
    }
    return post, cost, record


def apply_request(payload: dict[str, Any]) -> dict[str, Any]:
    state = parse_state(payload.get("state"))
    action = parse_action(payload.get("action"))
    try:
        _, _, record = apply_action(state, action, payload.get("parameters"))
        return record
    except (OperationalError, ComparisonError) as exc:
        return _transition_rejected(state, action, str(exc))


def family_payload(state: State) -> list[dict[str, Any]]:
    return [event_payload(event) for event in sorted(state)]


def compare_states(source: State, target: State, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    operational_weights(parameters)
    return compare_families(family_payload(source), family_payload(target), parameters)


def evaluate_actions(source: State, actions: Iterable[Action], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    source = validate_state(source)
    current = source
    records = []
    total = Fraction(0)
    action_list = list(actions)
    for index, action in enumerate(action_list, 1):
        try:
            current, cost, record = apply_action(current, action, parameters)
        except (OperationalError, ComparisonError) as exc:
            raise OperationalError(f"Paso {index}: {exc}") from exc
        record["step"] = index
        total += cost
        record["cumulative_cost"] = rational_payload(total)
        records.append(record)
    reduced = [record for record in records if record["effective"]]
    effective_actions = [action for action, record in zip(action_list, records) if record["effective"]]
    if len(effective_actions) < len(action_list):
        revalidated_reduction = evaluate_actions(source, effective_actions, parameters)
        reduced_steps = revalidated_reduction["steps"]
        reduced_cost = Fraction(revalidated_reduction["cost"]["exact"])
    else:
        reduced_steps = reduced
        reduced_cost = total
    return {
        "source": state_payload(source), "target": state_payload(current), "steps": records,
        "step_count": len(records), "length": len(records), "cost": rational_payload(total),
        "qualitative_sequence": [record["action"]["kind"] for record in records],
        "reduced": len(reduced) == len(records),
        "reduction": {"removed_stationary_steps": len(records) - len(reduced), "removed_inert_steps": len(records) - len(reduced),
                      "revalidated": True, "steps": reduced_steps, "cost": rational_payload(reduced_cost)},
    }


def trajectory_request(payload: dict[str, Any]) -> dict[str, Any]:
    source = parse_state(payload.get("source"), "origen")
    raw_actions = payload.get("actions", [])
    if not isinstance(raw_actions, list):
        raise OperationalError("actions debe ser una lista")
    result = evaluate_actions(source, (parse_action(item) for item in raw_actions), payload.get("parameters"))
    expected = parse_state(payload["target"], "destino") if "target" in payload else None
    if expected is not None:
        comparison = compare_states(source, expected, payload.get("parameters"))
        total = Fraction(result["cost"]["exact"])
        distance = Fraction(comparison["distance"]["exact"])
        reaches = parse_state(result["target"]) == expected
        renormalization_free = all(not record["normalization"] or not record["normalization"]["effective"] for record in result["steps"])
        result["requested_target"] = state_payload(expected)
        result["reaches_requested_target"] = reaches
        result["static_distance"] = comparison
        result["comparison"] = {
            "trajectory_cost": rational_payload(total), "D_gamma": rational_payload(distance),
            "gap": rational_payload(total - distance), "certifies_delta_T": False,
            "renormalization_free": renormalization_free,
            "equal_to_D_gamma": reaches and total == distance,
            "D_gamma_le_trajectory": distance <= total if reaches and renormalization_free else None,
            "statement": "La comparación con Dγ describe esta trayectoria concreta; incluso una igualdad no certifica el ínfimo global δ_T.",
        }
    return result


def evaluate_word(source: State, word: Iterable[Action], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evalúa una palabra operacional y localiza exactamente el primer fallo."""
    actions = list(word)
    try:
        return {"admissible": True, "trajectory": evaluate_actions(source, actions, parameters), "first_failure": None}
    except OperationalError as exc:
        text = str(exc)
        step = None
        if text.startswith("Paso "):
            try:
                step = int(text.split(":", 1)[0].split()[1])
            except (ValueError, IndexError):
                step = None
        return {"admissible": False, "trajectory": None, "first_failure": {"step": step, "reason": text}}


def words_equivalent_at(source: State, left: Iterable[Action], right: Iterable[Action], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Decide equivalencia local de dos palabras, sin afirmación global."""
    first = evaluate_word(source, left, parameters)
    second = evaluate_word(source, right, parameters)
    equivalent = first["admissible"] and second["admissible"] and first["trajectory"]["target"] == second["trajectory"]["target"]
    return {"equivalent_at_state": equivalent, "global_equivalence_claim": False, "left": first, "right": second}


def commutes_at(source: State, first: Action, second: Action, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Comprueba conmutación local e igualdad adicional de costes de rama."""
    comparison = words_equivalent_at(source, [first, second], [second, first], parameters)
    left, right = comparison["left"], comparison["right"]
    equal_cost = False
    if left["admissible"] and right["admissible"]:
        equal_cost = left["trajectory"]["cost"]["exact"] == right["trajectory"]["cost"]["exact"]
    return {
        "commutes_at_state": comparison["equivalent_at_state"],
        "equal_branch_cost": equal_cost,
        "operational_diamond": comparison["equivalent_at_state"] and equal_cost,
        "global_commutativity_claim": False,
        "branches": {"first_then_second": left, "second_then_first": right},
    }


def algebra_request(payload: dict[str, Any]) -> dict[str, Any]:
    source = parse_state(payload.get("source"), "origen")
    mode = payload.get("mode", "commutes_at")
    if mode == "evaluate_word":
        word = payload.get("word")
        if not isinstance(word, list):
            raise OperationalError("word debe ser una lista")
        return evaluate_word(source, [parse_action(action) for action in word], payload.get("parameters"))
    if mode == "equivalent_at":
        left, right = payload.get("left"), payload.get("right")
        if not isinstance(left, list) or not isinstance(right, list):
            raise OperationalError("left y right deben ser listas de acciones")
        return words_equivalent_at(source, [parse_action(action) for action in left], [parse_action(action) for action in right], payload.get("parameters"))
    if mode == "commutes_at":
        return commutes_at(source, parse_action(payload.get("first")), parse_action(payload.get("second")), payload.get("parameters"))
    raise OperationalError("mode debe ser evaluate_word, equivalent_at o commutes_at")


def _auxiliary_pitch(state: State, target: State) -> int:
    occupied = {h for h, u, v in target if u == 0 and v == 1}
    base = next(iter(state))[0]
    for magnitude in itertools.count(0):
        for candidate in ({0} if magnitude == 0 else {magnitude, -magnitude}):
            if candidate != base and candidate not in occupied:
                return candidate
    raise AssertionError("Los enteros son infinitos")


def constructive_actions(source: State, target: State) -> list[Action]:
    current = source
    actions: list[Action] = []
    while len(current) > 1:
        event = sorted(current)[0]
        action = Action("del", event)
        current, _, _ = apply_action(current, action)
        actions.append(action)
    sole = next(iter(current))
    auxiliary_h = _auxiliary_pitch(current, target)
    if sole[0] != auxiliary_h:
        action = Action("h", sole, auxiliary_h - sole[0])
        current, _, _ = apply_action(current, action)
        actions.append(action)
    auxiliary = next(iter(current))
    for event in sorted(target):
        action = Action("ins", event)
        current, _, _ = apply_action(current, action)
        actions.append(action)
    action = Action("del", auxiliary)
    current, _, _ = apply_action(current, action)
    actions.append(action)
    if current != target:
        raise AssertionError("La construcción de alcanzabilidad no llegó al destino")
    return actions


def reachability_request(payload: dict[str, Any]) -> dict[str, Any]:
    source = parse_state(payload.get("source"), "origen")
    target = parse_state(payload.get("target"), "destino")
    actions = constructive_actions(source, target)
    result = evaluate_actions(source, actions, payload.get("parameters"))
    result["requested_target"] = state_payload(target)
    result["reaches_requested_target"] = parse_state(result["target"]) == target
    result["bound"] = len(source) + len(target) + 1
    result["within_bound"] = len(actions) <= result["bound"]
    result["static_distance"] = compare_states(source, target, payload.get("parameters"))
    result["statement"] = "Testigo constructivo exacto de alcanzabilidad; su coste no se presenta como δ_T."
    return result


def _candidate_actions(state: State, target: State, envelope: dict[str, Any], mode: str) -> list[Action]:
    actions: set[Action] = {Action("id")} if envelope["include_identity"] else set()
    if mode == "TARGET_GUIDED":
        deltas_h = {b[0] - a[0] for a in state for b in target}
        onset_deltas = {b[1] - a[1] for a in state for b in target}
        offset_deltas = {b[2] - a[2] for a in state for b in target}
        insertions = set(target)
    else:
        deltas_h = set(envelope["pitch_deltas"])
        onset_deltas = set(envelope["onset_deltas"])
        offset_deltas = set(envelope["offset_deltas"])
        insertions = set(envelope["insertions"])
    for event in state:
        actions.add(Action("del", event))
        actions.update(Action("h", event, delta) for delta in deltas_h)
        actions.update(Action("u", event, delta) for delta in onset_deltas)
        actions.update(Action("v", event, delta) for delta in offset_deltas)
    actions.update(Action("ins", event) for event in insertions)
    return sorted(actions, key=lambda a: str(action_payload(a)))


def _parse_envelope(raw: Any) -> dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise OperationalError("envelope debe ser un objeto")
    def bounded_int(name: str, default: int, limit: int) -> int:
        value = raw.get(name, default)
        if type(value) is not int or not 1 <= value <= limit:
            raise OperationalError(f"{name} debe ser un entero entre 1 y {limit}")
        return value
    pitch = raw.get("pitch_deltas", [-12, -1, 1, 12])
    timing = raw.get("time_deltas", ["-1/2", "-1/4", "1/4", "1/2"])
    onset = raw.get("onset_deltas", timing)
    offset = raw.get("offset_deltas", timing)
    insertions = raw.get("insertions", [])
    if not isinstance(pitch, list) or any(type(x) is not int for x in pitch):
        raise OperationalError("pitch_deltas debe ser una lista de enteros")
    if not isinstance(onset, list) or not isinstance(offset, list) or not isinstance(insertions, list):
        raise OperationalError("onset_deltas, offset_deltas e insertions deben ser listas")
    timeout = raw.get("timeout_ms", 1500)
    if type(timeout) is not int or not 50 <= timeout <= 10000:
        raise OperationalError("timeout_ms debe estar entre 50 y 10000")
    for flag in ("include_identity", "exclude_stationary", "materialize_full_graph"):
        if flag in raw and type(raw[flag]) is not bool:
            raise OperationalError(f"{flag} debe ser booleano")
    return {
        "max_steps": bounded_int("max_steps", 4, 12), "max_nodes": bounded_int("max_nodes", 1200, 20000),
        "max_paths": bounded_int("max_paths", 64, 256),
        "timeout_ms": timeout, "pitch_deltas": sorted(set(pitch)),
        "onset_deltas": sorted({_fraction(x, "onset_delta") for x in onset}),
        "offset_deltas": sorted({_fraction(x, "offset_delta") for x in offset}),
        "insertions": sorted({_event(x, "insertion") for x in insertions}),
        "include_identity": bool(raw.get("include_identity", False)),
        "exclude_stationary": bool(raw.get("exclude_stationary", True)),
        "materialize_full_graph": bool(raw.get("materialize_full_graph", True)),
    }


def _tarjan_scc_graph(node_ids: list[str], adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan SCC sobre adjacencia simple (sets de vecinos).

    Ordena componentes por -cardinality y luego lex.
    """
    allowed = set(node_ids)
    filtered: dict[str, list[str]] = {}
    for n in node_ids:
        nbs = sorted({nb for nb in adjacency.get(n, []) if nb in allowed})
        filtered[n] = nbs
    index_counter = itertools.count()
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(v0: str) -> None:
        call_stack: list[tuple[str, int, list[str]]] = [(v0, 0, filtered[v0])]
        indices[v0] = next(index_counter)
        lowlink[v0] = indices[v0]
        stack.append(v0)
        on_stack.add(v0)
        while call_stack:
            node, idx, neighbors = call_stack[-1]
            if idx < len(neighbors):
                w = neighbors[idx]
                call_stack[-1] = (node, idx + 1, neighbors)
                if w not in indices:
                    indices[w] = next(index_counter)
                    lowlink[w] = indices[w]
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, 0, filtered[w]))
                elif w in on_stack:
                    lowlink[node] = min(lowlink[node], indices[w])
            else:
                if lowlink[node] == indices[node]:
                    comp: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == node:
                            break
                    components.append(sorted(comp))
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

    for node in sorted(node_ids):
        if node not in indices:
            strongconnect(node)
    components.sort(key=lambda comp: (-len(comp), comp))
    return components


def _scc_metrics(
    node_ids: list[str],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calcula SCCs y métricas sobre G_R materializado.

    Returns diccionario con: scc_count, nontrivial_scc_count, largest_scc_*,
    bidirectional_nonstationary_pair_count.
    """
    if not node_ids:
        return {
            "scc_count": 0,
            "nontrivial_scc_count": 0,
            "largest_scc_cardinality": 0,
            "largest_scc_edge_count": 0,
            "largest_scc_state_ids": [],
            "bidirectional_nonstationary_pair_count": 0,
        }
    adj_plain: dict[str, set[str]] = {n: set() for n in node_ids}
    dir_edges_no_loop: set[tuple[str, str]] = set()
    for e in edges:
        s, t = e["source"], e["target"]
        if s in adj_plain and t in adj_plain:
            adj_plain[s].add(t)
            if s != t:
                dir_edges_no_loop.add((s, t))
    adj_list = {n: sorted(nb) for n, nb in adj_plain.items()}
    sccs = _tarjan_scc_graph(node_ids, adj_list)
    nontrivial = [c for c in sccs if len(c) >= 2]
    scc_count = len(sccs)
    nontrivial_count = len(nontrivial)
    if sccs:
        largest = sccs[0]
        largest_set = set(largest)
        largest_edge_count = sum(
            1 for e in edges
            if e["source"] in largest_set and e["target"] in largest_set
        )
    else:
        largest = []
        largest_edge_count = 0
    bidirectional = 0
    checked: set[tuple[str, str]] = set()
    if nontrivial:
        for comp in nontrivial:
            for a in comp:
                for b in comp:
                    if a >= b:
                        continue
                    pair = (a, b)
                    if pair in checked:
                        continue
                    checked.add(pair)
                    if (a, b) in dir_edges_no_loop and (b, a) in dir_edges_no_loop:
                        bidirectional += 1
    return {
        "scc_count": scc_count,
        "nontrivial_scc_count": nontrivial_count,
        "largest_scc_cardinality": len(largest),
        "largest_scc_edge_count": largest_edge_count,
        "largest_scc_state_ids": list(largest),
        "bidirectional_nonstationary_pair_count": bidirectional,
        "scc_components": [
            {
                "component_id": f"scc-{i+1}-size-{len(c)}",
                "cardinality": len(c),
                "state_ids": list(c),
            }
            for i, c in enumerate(sccs)
        ],
    }


def _blocked_scc(reason: str) -> dict[str, Any]:
    """SCC placeholder cuando el pipeline se bloquea antes de calcularlas."""
    return {
        "computed": False,
        "scc_count": 0,
        "nontrivial_scc_count": 0,
        "largest_scc_cardinality": 0,
        "largest_scc_edge_count": 0,
        "largest_scc_state_ids": [],
        "bidirectional_nonstationary_pair_count": 0,
        "scc_components": [],
        "blocking_reason": reason,
    }


def _resolve_graph_status(
    edge_materialization_complete: bool,
    action_policy_mismatch: bool,
    v_ids: set[str],
    edges: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Decide graph_status y si procede calcular SCC.

    - ACTION_POLICY_MISMATCH e INCOMPLETE_EDGE_MATERIALIZATION bloquean antes de SCC.
    - Sólo con E_R completo y política coherente se calculan SCC; si la mayor es
      < 2, se reporta INSUFFICIENT_NONTRIVIAL_SCC (resultado interpretable).
    """
    if action_policy_mismatch:
        return "ACTION_POLICY_MISMATCH", _blocked_scc("ACTION_POLICY_MISMATCH")
    if not edge_materialization_complete:
        return "INCOMPLETE_EDGE_MATERIALIZATION", _blocked_scc("INCOMPLETE_EDGE_MATERIALIZATION")
    scc_data = _scc_metrics(sorted(v_ids), edges)
    scc_data["computed"] = True
    graph_status = "INSUFFICIENT_NONTRIVIAL_SCC" if scc_data["largest_scc_cardinality"] < 2 else "G_R_MATERIALIZED"
    return graph_status, scc_data


def _expected_reverse_action(action: Action) -> tuple[Action | None, str]:
    """Dada una acción forward, construye la acción inversa esperada (ingenuamente).

    Returns (reverse_action_or_None, failure_reason).
    Si failure_reason no es vacío, la definición de reverse no es aplicable.
    """
    if action.kind == "id":
        return Action("id"), ""
    if action.event is None:
        return None, "REVERSE_ACTION_NOT_DEFINED"
    ev = action.event
    if action.kind == "h":
        if not isinstance(action.delta, int):
            return None, "REVERSE_ACTION_NOT_DEFINED"
        rev = Action("h", ev, -action.delta)
        return rev, ""
    if action.kind in {"u", "v"}:
        if not isinstance(action.delta, Fraction):
            return None, "REVERSE_ACTION_NOT_DEFINED"
        rev = Action(action.kind, ev, -action.delta)
        return rev, ""
    if action.kind == "ins":
        return Action("del", ev), ""
    if action.kind == "del":
        return Action("ins", ev), ""
    return None, "REVERSE_ACTION_NOT_DEFINED"


def _reversibility_diagnostics_sample(
    nodes: dict[str, State],
    edges: list[dict[str, Any]],
    parameters: dict[str, Any] | None,
    sample_size: int = 15,
    rng_seed: int = 8002,
) -> list[dict[str, Any]]:
    """Diagnóstico de reversibilidad sobre una muestra de aristas no estacionarias.

    Para cada arista X -> Y intenta construir la acción inversa esperada y comprobar
    si realmente devuelve a X canónico.
    """
    nonstat = [e for e in edges if e["source"] != e["target"]]
    if not nonstat:
        return []
    import random as _r
    rng = _r.Random(rng_seed)
    sample = list(nonstat)
    rng.shuffle(sample)
    sample = sample[:sample_size]
    target_ids = set(nodes.keys())
    dir_set = {(e["source"], e["target"]) for e in edges}
    records: list[dict[str, Any]] = []
    for edge in sample:
        src_id = edge["source"]
        tgt_id = edge["target"]
        fwd_action = parse_action(edge["action"])
        rev_action, def_reason = _expected_reverse_action(fwd_action)
        rec: dict[str, Any] = {
            "source_state_id": src_id,
            "target_state_id": tgt_id,
            "source_state": state_payload(nodes[src_id]) if src_id in nodes else None,
            "target_state": state_payload(nodes[tgt_id]) if tgt_id in nodes else None,
            "forward_action": action_payload(fwd_action),
            "reverse_action_expected": action_payload(rev_action) if rev_action else None,
            "reverse_action_defined": rev_action is not None,
            "reverse_action_admissible": False,
            "reverse_result_state_id": None,
            "reverse_result_state": None,
            "reverse_matches_source": False,
            "reverse_edge_present": False,
            "failure_reason": None,
            "canonicalization_classification": None,
        }
        if def_reason:
            rec["failure_reason"] = def_reason
            records.append(rec)
            continue
        assert rev_action is not None
        X_state = nodes.get(src_id)
        Y_state = nodes.get(tgt_id)
        if X_state is None or Y_state is None:
            rec["failure_reason"] = "REVERSE_TARGET_OUTSIDE_V_R"
            records.append(rec)
            continue
        try:
            post_rev, _, rec_rev = apply_action(Y_state, rev_action, parameters)
            rec["reverse_action_admissible"] = True
            post_id = state_id(post_rev)
            rec["reverse_result_state_id"] = post_id
            rec["reverse_result_state"] = state_payload(post_rev)
            matches = (post_id == src_id)
            rec["reverse_matches_source"] = matches
            rev_edge_present = (tgt_id, src_id) in dir_set
            rec["reverse_edge_present"] = rev_edge_present
            if not matches:
                if post_id not in target_ids:
                    rec["failure_reason"] = "REVERSE_TARGET_OUTSIDE_V_R"
                else:
                    rec["failure_reason"] = "REVERSE_RESULT_DIFFERENT_CANONICAL_STATE"
                    # Clasificación explícita de canonicalización (requisito 5).
                    if (rec_rev.get("normalization") or {}).get("effective"):
                        rec["canonicalization_classification"] = "NORMALIZATION_INFORMATION_LOSS"
                    else:
                        rec["canonicalization_classification"] = "CANONICALIZATION_BUG"
            else:
                if not rev_edge_present:
                    rec["failure_reason"] = "REVERSE_EDGE_NOT_MATERIALIZED"
                else:
                    rec["failure_reason"] = "OK"
        except (OperationalError, ComparisonError) as exc:
            msg = str(exc)
            if "no pertenece al estado" in msg or "ya existe" in msg or "inicio < fin" in msg or "descriptor" in msg:
                rec["failure_reason"] = "REVERSE_ACTION_NOT_ADMISSIBLE"
            else:
                rec["failure_reason"] = "REVERSE_RESULT_INVALID"
        records.append(rec)
    return records


def search_request(payload: dict[str, Any]) -> dict[str, Any]:
    source = parse_state(payload.get("source"), "origen")
    target = parse_state(payload.get("target"), "destino")
    mode = payload.get("mode", "TARGET_GUIDED")
    if mode not in {"TARGET_GUIDED", "DECLARED_GRID"}:
        raise OperationalError("mode debe ser TARGET_GUIDED o DECLARED_GRID")
    envelope = _parse_envelope(payload.get("envelope"))
    profile = operational_weights(payload.get("parameters"))
    if mode == "TARGET_GUIDED" and not envelope["insertions"]:
        envelope["insertions"] = sorted(target)
    started = time.monotonic()
    params = payload.get("parameters")
    source_id0 = state_id(source)
    target_id0 = state_id(target)

    # ============================================================
    # FASE A · DESCUBRIMIENTO V_R  (heap Dijkstra; SIN materializar aristas)
    # ============================================================
    counter = itertools.count()
    start_key = (source, 0)
    queue: list[tuple[Fraction, int, State, int]] = [(Fraction(0), next(counter), source, 0)]
    best: dict[tuple[State, int], Fraction] = {start_key: Fraction(0)}
    parent: dict[tuple[State, int], tuple[tuple[State, int], Action, dict[str, Any]]] = {}
    nodes: dict[str, State] = {source_id0: source}
    generated_transitions = 0
    expanded = 0
    found: tuple[State, int] | None = start_key if source == target else None
    found_cost: Fraction | None = Fraction(0) if source == target else None
    truncated: str | None = None
    timeout_reached = False
    node_limit_reached = False
    step_limit_reached_any = False

    while queue:
        if (time.monotonic() - started) * 1000 >= envelope["timeout_ms"]:
            truncated = "timeout"
            timeout_reached = True
            break
        cost, _, state, depth = heapq.heappop(queue)
        if found_cost is not None and cost > found_cost and not envelope["materialize_full_graph"]:
            break
        key = (state, depth)
        if cost != best.get(key):
            continue
        if state == target:
            if found is None or cost < found_cost or (cost == found_cost and depth < found[1]):
                found = key
                found_cost = cost
            continue
        expanded += 1
        if depth >= envelope["max_steps"]:
            step_limit_reached_any = True
            continue
        for action in _candidate_actions(state, target, envelope, mode):
            try:
                post, edge_cost, record = apply_action(state, action, params)
            except (OperationalError, ComparisonError):
                continue
            if post == state and envelope["exclude_stationary"]:
                continue
            post_id = state_id(post)
            nodes[post_id] = post
            generated_transitions += 1
            next_key = (post, depth + 1)
            next_cost = cost + edge_cost
            if next_cost < best.get(next_key, Fraction(10**100)):
                best[next_key] = next_cost
                parent[next_key] = (key, action, record)
                heapq.heappush(queue, (next_cost, next(counter), post, depth + 1))
            if len(nodes) >= envelope["max_nodes"]:
                truncated = "max_nodes"
                node_limit_reached = True
                break
        if truncated:
            break

    frontier_size_at_stop = len(queue)
    total_possible_expanded = len(nodes)
    unexpanded_node_count = max(0, total_possible_expanded - expanded)

    # ============================================================
    # FASE B · MATERIALIZACIÓN E_R  (V_R congelado; TODAS las aristas internas)
    # ============================================================
    # La política efectiva de materialización es ÚNICA y NO depende de la fase
    # de descubrimiento ni de las diferencias al target: se deriva exclusivamente
    # del envelope declarado. Así toda arista de E_R es deducible de los campos
    # exportados (effective_pitch/onset/offset_deltas, effective_insertions,
    # effective_deletions, identity_action_policy).
    mat_pitch_sorted = sorted(set(envelope["pitch_deltas"]))
    mat_onset_sorted = sorted(set(envelope["onset_deltas"]))
    mat_offset_sorted = sorted(set(envelope["offset_deltas"]))
    mat_insertions_sorted = sorted(set(envelope["insertions"]))
    effective_deletions_sorted = sorted({ev for X_state in nodes.values() for ev in X_state})

    v_ids = set(nodes.keys())
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str]] = set()
    edges_generated_phase2 = 0
    candidate_actions_evaluated = 0
    edge_materialization_source_count = 0
    nodes_with_outgoing: set[str] = set()

    # La materialización es determinista y acotada por |V_R| × |acciones|. NO se
    # interrumpe por timeout: si no recorre TODOS los estados, el pipeline se
    # bloquea con INCOMPLETE_EDGE_MATERIALIZATION (ver validación más abajo).
    for sid in sorted(v_ids):
        X_state = nodes[sid]
        edge_materialization_source_count += 1

        # Generar TODAS las acciones admisibles según la política efectiva.
        actions_X: list[Action] = []
        if envelope["include_identity"]:
            actions_X.append(Action("id"))
        for ev in X_state:
            actions_X.append(Action("del", ev))
            for dh in mat_pitch_sorted:
                actions_X.append(Action("h", ev, dh))
            for du in mat_onset_sorted:
                actions_X.append(Action("u", ev, du))
            for dv in mat_offset_sorted:
                actions_X.append(Action("v", ev, dv))
        for ev_ins in mat_insertions_sorted:
            actions_X.append(Action("ins", ev_ins))

        for action in actions_X:
            candidate_actions_evaluated += 1
            try:
                post, edge_cost, record = apply_action(X_state, action, params)
            except (OperationalError, ComparisonError):
                continue
            # exclude_stationary sólo aplica a acciones NO identidad que dejan el
            # estado exactamente igual (p. ej. delta=0). La identidad explícita
            # (kind="id") es un concepto distinto y se rige por include_identity.
            if action.kind != "id" and post == X_state and envelope["exclude_stationary"]:
                continue
            post_id = state_id(post)
            if post_id not in v_ids:
                continue
            serialized_action = str(action_payload(action))
            edge_key = (sid, post_id, serialized_action)
            if edge_key in edge_keys:
                continue
            edge_keys.add(edge_key)
            edges.append({
                "source": sid,
                "target": post_id,
                "action": action_payload(action),
                "cost": rational_payload(edge_cost),
                "normalization_effective": bool(record["normalization"] and record["normalization"]["effective"]),
            })
            edges_generated_phase2 += 1
            nodes_with_outgoing.add(sid)

    internal_edges_materialized = len(edges)
    edge_materialization_complete = (edge_materialization_source_count == len(nodes))
    nodes_without_outgoing = sorted(v_ids - nodes_with_outgoing)

    # Validación automática: TODA arista de E_R debe ser deducible de la política
    # efectiva exportada. Si no, se bloquea la certificación.
    action_policy_violations: list[dict[str, Any]] = []
    for edge in edges:
        action = parse_action(edge["action"])
        reason = None
        if action.kind == "id":
            if not envelope["include_identity"]:
                reason = "identity_action_not_allowed"
        elif action.kind == "h":
            if action.delta not in mat_pitch_sorted:
                reason = f"pitch_delta_{action.delta}_not_in_effective_pitch_deltas"
        elif action.kind == "u":
            if action.delta not in mat_onset_sorted:
                reason = f"onset_delta_{action.delta}_not_in_effective_onset_deltas"
        elif action.kind == "v":
            if action.delta not in mat_offset_sorted:
                reason = f"offset_delta_{action.delta}_not_in_effective_offset_deltas"
        elif action.kind == "ins":
            if action.event not in mat_insertions_sorted:
                reason = "insertion_event_not_in_effective_insertions"
        elif action.kind == "del":
            if action.event not in effective_deletions_sorted:
                reason = "deletion_event_not_in_effective_deletions"
        else:
            reason = f"unknown_action_kind_{action.kind}"
        if reason is not None:
            action_policy_violations.append({
                "edge": {"source": edge["source"], "target": edge["target"], "action": edge["action"]},
                "reason": reason,
            })
    action_policy_mismatch = bool(action_policy_violations)

    # ============================================================
    # Reconstrucción del best_path (usa parents de FASE A; sigue siendo válido)
    # ============================================================
    path: list[dict[str, Any]] = []
    total: Fraction | None = None
    if found is not None:
        total = best[found]
        cursor = found
        while cursor != start_key:
            previous, action, record = parent[cursor]
            path.append({"action": action_payload(action), "transition": record})
            cursor = previous
        path.reverse()

    # ============================================================
    # Truncation enum + flags
    # ============================================================
    if found is not None:
        status = "EXACT_WITHIN_RESTRICTION" if mode == "DECLARED_GRID" and truncated is None else "FOUND_CANDIDATE"
        truncation_status = "COMPLETE_WITHIN_ENVELOPE" if (
            status == "EXACT_WITHIN_RESTRICTION" and not node_limit_reached and not timeout_reached
        ) else (
            "TRUNCATED_BY_TIMEOUT" if timeout_reached else
            "TRUNCATED_BY_NODE_LIMIT" if node_limit_reached else
            "COMPLETE_WITHIN_ENVELOPE"
        )
    elif truncated:
        status = "TRUNCATED_BY_TIMEOUT" if truncated == "timeout" else "TRUNCATED_BY_NODE_LIMIT"
        truncation_status = status
    else:
        status = "NOT_FOUND_WITHIN_RESTRICTION"
        if node_limit_reached:
            truncation_status = "TRUNCATED_BY_NODE_LIMIT"
        elif timeout_reached:
            truncation_status = "TRUNCATED_BY_TIMEOUT"
        else:
            truncation_status = "COMPLETE_WITHIN_ENVELOPE"

    # Estado de la FASE DE DESCUBRIMIENTO (independiente de la materialización).
    if timeout_reached:
        discovery_status = "TRUNCATED_BY_TIMEOUT"
    elif node_limit_reached:
        discovery_status = "TRUNCATED_BY_NODE_LIMIT"
    elif step_limit_reached_any:
        discovery_status = "TRUNCATED_BY_STEP_LIMIT"
    else:
        discovery_status = "COMPLETE_WITHIN_ENVELOPE"

    discovered_node_count = len(nodes)
    expanded_during_discovery_count = expanded

    # ============================================================
    # SCCs SOLO tras E_R completo y política coherente.
    # ============================================================
    graph_status, scc_data = _resolve_graph_status(
        edge_materialization_complete, action_policy_mismatch, v_ids, edges
    )

    self_loops_materialized = sum(1 for e in edges if e["source"] == e["target"])

    # ============================================================
    # Action generation policy + effective policies export
    # ============================================================
    action_generation_policy = {
        "phase_split": "V_R_DISCOVERY_THEN_E_R_MATERIALIZATION",
        "discovery_strategy": "dijkstra_cost_guided_with_max_steps_depth",
        "materialization_strategy": "closed_internal_edges_over_V_R_all_admissible_actions",
        "mode": mode,
        "materialize_full_graph_flag": envelope["materialize_full_graph"],
        "include_identity": envelope["include_identity"],
        "exclude_stationary": envelope["exclude_stationary"],
        "statement": (
            "G_R es subgrafo operacional finito materializado sobre V_R; "
            "aristas internas cerradas; NO es sistema operacional completo."
        ),
    }
    identity_action_policy = {
        "include_identity": envelope["include_identity"],
        "identity_action": "kind='id': deja el estado exactamente igual, coste 0; sólo se materializa si include_identity=true.",
        "stationary_action": "acción h/u/v (p. ej. delta=0) cuyo estado post coincide con el pre; excluida si exclude_stationary=true.",
        "self_loop": "arista X->X; sólo puede surgir de identity_action (include_identity=true) o de stationary_action no excluida.",
        "exclude_stationary": envelope["exclude_stationary"],
        "self_loops_materialized": self_loops_materialized,
    }
    normalization_policy = {
        "rule": "affine_min_u_to_0_max_v_to_1_per_state",
        "per_action_recorded": True,
        "canonically_inert_recorded": True,
        "statement": "La normalización afín puede producir pérdida de información en roundtrips de u/v sobre fronteras temporales.",
    }

    result: dict[str, Any] = {
        "mode": mode, "status": status, "global_optimality_claim": False,
        "graph_status": graph_status,
        "edge_materialization_complete": bool(edge_materialization_complete),
        "edge_materialization_source_count": edge_materialization_source_count,
        "discovered_node_count": discovered_node_count,
        "expanded_during_discovery_count": expanded_during_discovery_count,
        "candidate_actions_evaluated": candidate_actions_evaluated,
        "internal_edges_materialized": internal_edges_materialized,
        "nodes_with_outgoing_internal_edges": len(nodes_with_outgoing),
        "nodes_without_outgoing_internal_edges": len(nodes_without_outgoing),
        "action_policy_mismatch": bool(action_policy_mismatch),
        "action_policy_violations": action_policy_violations,
        "cost_profile": {name: rational_payload(value) for name, value in profile.items()},
        "exact_within_restriction": status == "EXACT_WITHIN_RESTRICTION",
        "statement": ("Óptimo sólo dentro de la rejilla finita declarada." if status == "EXACT_WITHIN_RESTRICTION"
                      else "Resultado heurístico/restringido; no identifica el ínfimo global δ_T."),
        "truncated_by": truncated,
        "truncation_status": truncation_status,
        "discovery_status": discovery_status,
        "node_limit_reached": bool(node_limit_reached),
        "step_limit_reached": bool(step_limit_reached_any),
        "timeout_reached": bool(timeout_reached),
        "frontier_size_at_stop": frontier_size_at_stop,
        "unexpanded_node_count": unexpanded_node_count,
        "expanded_node_count": expanded,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        "envelope": {
            **envelope,
            "onset_deltas": [_exact(x) for x in envelope["onset_deltas"]],
            "offset_deltas": [_exact(x) for x in envelope["offset_deltas"]],
            "insertions": [event_payload(x) for x in envelope["insertions"]],
        },
        "action_generation_policy": action_generation_policy,
        "identity_action_policy": identity_action_policy,
        "effective_pitch_deltas": sorted(mat_pitch_sorted),
        "effective_onset_deltas": [_exact(x) for x in mat_onset_sorted],
        "effective_offset_deltas": [_exact(x) for x in mat_offset_sorted],
        "effective_insertions": [event_payload(x) for x in mat_insertions_sorted],
        "effective_deletions": [event_payload(x) for x in effective_deletions_sorted],
        "normalization_policy": normalization_policy,
        "graph_scc_statistics": scc_data,
        "best_path": path, "best_cost": rational_payload(total) if total is not None else None,
        "global_upper_bound": rational_payload(total) if total is not None else None,
        "nodes_expanded": expanded,
        "edges_generated": generated_transitions,
        "edges_materialized_phase2": edges_generated_phase2,
        "unique_multiedges": len(edges),
        "explored_graph": {
            "nodes": [{"id": key, "state": state_payload(value)} for key, value in sorted(nodes.items())],
            "edges": edges,
            "materialized_full_graph": bool(edge_materialization_complete),
            "edge_materialization_complete": bool(edge_materialization_complete),
            "construction": "V_R_THEN_E_R_TWO_PHASE",
            "node_set_frozen_before_edge_materialization": True,
            "edge_materialization_source_count": edge_materialization_source_count,
            "node_count": discovered_node_count,
        },
        "static_distance": compare_states(source, target, params),
    }

    # Diagnóstico reversibilidad sample (antes de analyze_processes)
    if len(edges) >= 1:
        result["reversibility_diagnostics_sample"] = _reversibility_diagnostics_sample(
            nodes, edges, params, sample_size=15, rng_seed=8002
        )

    process_analysis = analyze_processes(result["explored_graph"], source_id0, target_id0, envelope["max_paths"])
    if status != "EXACT_WITHIN_RESTRICTION":
        process_analysis["best_found_reduced_paths"] = process_analysis.pop("optimal_reduced_paths")
        process_analysis["process_class_status"] = "BEST_FOUND_IN_INCOMPLETE_OR_HEURISTIC_EXPLORATION"
        process_analysis["mu_restricted"] = None
    elif process_analysis["optimal_paths_truncated"]:
        process_analysis["process_class_status"] = "OPTIMAL_PATH_ENUMERATION_TRUNCATED"
        process_analysis["mu_restricted"] = None
    else:
        process_analysis["process_class_status"] = "EXACT_WITHIN_RESTRICTION"
    result["process_analysis"] = process_analysis

    # AI diagnostics narrative (non-blocking; never raises)
    try:
        ai_enabled = ai_summaries.ai_enabled_from_request(payload)
        scc = scc_data or {}
        result["ai_search_summary"] = ai_summaries.summarize_search(
            ai_enabled,
            status=str(status),
            truncation_status=truncation_status,
            nodes_count=len(nodes),
            edges_count=len(edges),
            scc_count=int(scc.get("scc_count") or 0),
            nontrivial_scc_count=int(scc.get("nontrivial_scc_count") or 0),
            largest_scc_cardinality=int(scc.get("largest_scc_cardinality") or 0),
            bidirectional_nonstationary_pair_count=int(
                scc.get("bidirectional_nonstationary_pair_count") or 0
            ),
            effective_pitch_deltas=result.get("effective_pitch_deltas") or [],
            effective_onset_deltas=result.get("effective_onset_deltas") or [],
            effective_offset_deltas=result.get("effective_offset_deltas") or [],
        )
    except Exception as _e:  # noqa: BLE001 — blanket safe; never break search
        result["ai_search_summary"] = {
            "status": "SKIPPED_API_ERROR",
            "reason": f"Unexpected wrapper: {type(_e).__name__}: {_e}",
        }

    return result


def analyze_processes(graph: dict[str, Any], source: str, target: str, max_paths: int = 128) -> dict[str, Any]:
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in graph["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
    distance: dict[str, Fraction] = {source: Fraction(0)}
    queue: list[tuple[Fraction, int, str]] = [(Fraction(0), 0, source)]
    serial = itertools.count(1)
    while queue:
        cost, _, node = heapq.heappop(queue)
        if cost != distance[node]:
            continue
        for edge in adjacency.get(node, []):
            candidate = cost + Fraction(edge["cost"]["exact"])
            if candidate < distance.get(edge["target"], Fraction(10**100)):
                distance[edge["target"]] = candidate
                heapq.heappush(queue, (candidate, next(serial), edge["target"]))
    reverse: dict[str, list[dict[str, Any]]] = {}
    for edge in graph["edges"]:
        reverse.setdefault(edge["target"], []).append(edge)
    to_target: dict[str, Fraction] = {target: Fraction(0)}
    queue = [(Fraction(0), 0, target)]
    serial = itertools.count(1)
    while queue:
        cost, _, node = heapq.heappop(queue)
        if cost != to_target[node]:
            continue
        for edge in reverse.get(node, []):
            candidate = cost + Fraction(edge["cost"]["exact"])
            if candidate < to_target.get(edge["source"], Fraction(10**100)):
                to_target[edge["source"]] = candidate
                heapq.heappush(queue, (candidate, next(serial), edge["source"]))
    optimum = distance.get(target)
    intermediates = []
    if optimum is not None:
        intermediates = sorted(node for node in distance if node not in {source, target} and node in to_target and distance[node] + to_target[node] == optimum)
    diamonds = []
    for origin, outgoing in adjacency.items():
        for first, second in itertools.combinations(outgoing, 2):
            if first["target"] == second["target"]:
                continue
            for a in adjacency.get(first["target"], []):
                for b in adjacency.get(second["target"], []):
                    same_parameterized_actions = a["action"] == second["action"] and b["action"] == first["action"]
                    nonstationary_shape = a["target"] not in {first["target"], second["target"], origin}
                    equal_branch_cost = Fraction(first["cost"]["exact"]) + Fraction(a["cost"]["exact"]) == Fraction(second["cost"]["exact"]) + Fraction(b["cost"]["exact"])
                    if a["target"] == b["target"] and same_parameterized_actions and nonstationary_shape and equal_branch_cost:
                        diamonds.append({"origin": origin, "branches": [first["target"], second["target"]], "reconvergence": a["target"],
                                         "actions": [first["action"], second["action"]], "branch_cost": rational_payload(Fraction(first["cost"]["exact"]) + Fraction(a["cost"]["exact"]))})
                        break
                if diamonds and diamonds[-1]["origin"] == origin:
                    break
            if len(diamonds) >= 30:
                break
    optimal_paths: list[dict[str, Any]] = []
    paths_truncated = False
    if optimum is not None:
        def walk(node: str, states: list[str], edge_path: list[dict[str, Any]]) -> None:
            nonlocal paths_truncated
            if len(optimal_paths) >= max_paths:
                paths_truncated = True
                return
            if node == target:
                cumulative = Fraction(0)
                coordinates = [rational_payload(Fraction(0))]
                for edge in edge_path:
                    cumulative += Fraction(edge["cost"]["exact"])
                    coordinates.append(rational_payload(cumulative / optimum) if optimum else None)
                optimal_paths.append({
                    "states": states[:], "actions": [edge["action"] for edge in edge_path],
                    "cost": rational_payload(sum((Fraction(edge["cost"]["exact"]) for edge in edge_path), Fraction(0))),
                    "lambda_coordinates": coordinates,
                    "subpaths_optimal_in_graph": True,
                })
                return
            for edge in adjacency.get(node, []):
                nxt = edge["target"]
                if nxt in states or nxt not in to_target:
                    continue
                edge_cost = Fraction(edge["cost"]["exact"])
                if distance.get(node, Fraction(10**100)) + edge_cost + to_target[nxt] == optimum:
                    walk(nxt, [*states, nxt], [*edge_path, edge])
        walk(source, [source], [])
    parents = list(range(len(optimal_paths)))
    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    diamond_keys = {(d["origin"], frozenset(d["branches"]), d["reconvergence"]) for d in diamonds}
    for i, first in enumerate(optimal_paths):
        for j in range(i + 1, len(optimal_paths)):
            second = optimal_paths[j]
            if len(first["states"]) != len(second["states"]):
                continue
            differences = [k for k, pair in enumerate(zip(first["states"], second["states"])) if pair[0] != pair[1]]
            if len(differences) == 1:
                k = differences[0]
                if 0 < k < len(first["states"]) - 1 and (first["states"][k-1], frozenset({first["states"][k], second["states"][k]}), first["states"][k+1]) in diamond_keys:
                    parents[root(j)] = root(i)
    classes: dict[int, list[int]] = {}
    for index in range(len(optimal_paths)):
        classes.setdefault(root(index), []).append(index)
    intermediate_details = []
    if optimum is not None:
        for node in intermediates:
            intermediate_details.append({
                "state": node,
                "distance_from_source": rational_payload(distance[node]),
                "distance_to_target": rational_payload(to_target[node]),
                "intermediation_defect_graph": rational_payload(distance[node] + to_target[node] - optimum),
                "lambda_graph": rational_payload(distance[node] / optimum) if optimum else None,
            })
    indegree: dict[str, int] = {}
    for edge in graph["edges"]:
        indegree[edge["target"]] = indegree.get(edge["target"], 0) + 1
    branching = sorted(node for node, outgoing in adjacency.items() if len(outgoing) > 1)
    reconvergence = sorted(node for node, degree in indegree.items() if degree > 1)
    return {
        "graph_shortest_cost": rational_payload(optimum) if optimum is not None else None,
        "optimal_intermediates": intermediates,
        "intermediate_details": intermediate_details,
        "commutative_diamonds": diamonds,
        "optimal_reduced_paths": optimal_paths,
        "optimal_paths_truncated": paths_truncated,
        "restricted_process_classes": list(classes.values()),
        "mu_restricted": len(classes),
        "branching_states": branching,
        "reconvergence_states": reconvergence,
        "scope": "Sólo el multigrafo materializado por esta ejecución; no es una clasificación global de procesos.",
    }


def refinement_request(payload: dict[str, Any]) -> dict[str, Any]:
    raw_r = payload.get("R", "1")
    r = _fraction(raw_r, "R")
    if r <= 0:
        raise OperationalError("R debe ser positivo")
    omega_on = _fraction(payload.get("omega_on", "1"), "omega_on")
    if omega_on < 0:
        raise OperationalError("omega_on no puede ser negativo")
    maximum = payload.get("max_n", 32)
    if type(maximum) is not int or not 1 <= maximum <= 10000:
        raise OperationalError("max_n debe estar entre 1 y 10000")
    points = []
    for n in range(1, maximum + 1):
        rho = (1 + float(r)) ** (1 / n) - 1
        value = float(omega_on) * n * rho
        limit = float(omega_on) * math.log1p(float(r))
        points.append({"n": n, "rho_n": rho, "C_n": value, "value": value, "error_to_log": value - limit})
    return {"R": rational_payload(r), "omega_on": rational_payload(omega_on), "limit": float(omega_on) * math.log1p(float(r)), "points": points,
            "numeric_precision": "IEEE 754 binary64; sólo visual, nunca usada para igualdad de estados",
            "statement": "Demostración analítica numérica de la familia de §5.9.5; no es una búsqueda global de δ_T."}


def canonical_fixtures(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    # El perfil forma parte de los enunciados de §18 y no es configurable.
    params = {"omega_pc": 1, "omega_lin": 1, "omega_on": 1, "omega_off": 1, "gamma": 5}
    cases = []
    def check(name: str, obtained: Any, expected: Any) -> None:
        cases.append({"name": name, "status": "PASS" if obtained == expected else "FAIL", "expected": str(expected), "obtained": str(obtained)})
    conductor = frozenset({
        (0, Fraction(0), Fraction(1, 4)), (2, Fraction(1, 4), Fraction(3, 8)),
        (4, Fraction(1, 2), Fraction(3, 4)), (7, Fraction(3, 4), Fraction(1)),
    })
    check("conductor_estado_normalizado", validate_state(conductor), conductor)
    selected = (4, Fraction(1, 2), Fraction(3, 4))
    post, cost, record = apply_action(conductor, Action("h", selected, 1), params)
    check("conductor_altura_estado", (5, Fraction(1, 2), Fraction(3, 4)) in post, True)
    check("conductor_altura_coste", cost, Fraction(13, 12))
    post, cost, record = apply_action(conductor, Action("u", selected, Fraction(1, 8)), params)
    check("ataque_interno_estado", (4, Fraction(5, 8), Fraction(3, 4)) in post, True)
    check("ataque_interno_sin_renormalizar", record["normalization"]["effective"], False)
    check("ataque_interno_coste", cost, Fraction(1, 8))
    post, cost, record = apply_action(conductor, Action("v", selected, Fraction(1, 8)), params)
    check("terminacion_interna_estado", (4, Fraction(1, 2), Fraction(7, 8)) in post, True)
    check("terminacion_interna_sin_renormalizar", record["normalization"]["effective"], False)
    inserted = (5, Fraction(3, 8), Fraction(1, 2))
    with_insert, insert_cost, _ = apply_action(conductor, Action("ins", inserted), params)
    check("insercion_interna_coste", insert_cost, Fraction(5))
    back, delete_cost, _ = apply_action(with_insert, Action("del", inserted), params)
    check("dualidad_insercion_eliminacion", (back, delete_cost), (conductor, insert_cost))
    internal_deleted, internal_delete_cost, internal_delete_record = apply_action(conductor, Action("del", (2, Fraction(1, 4), Fraction(3, 8))), params)
    check("eliminacion_interna_cardinalidad", len(internal_deleted), 3)
    check("eliminacion_interna_coste", internal_delete_cost, Fraction(5))
    check("eliminacion_interna_sin_renormalizar", internal_delete_record["normalization"]["effective"], False)
    first_pitch = Action("h", selected, 1)
    second_event = (7, Fraction(3, 4), Fraction(1))
    second_pitch = Action("h", second_event, 2)
    branch_a, branch_a_first, _ = apply_action(conductor, first_pitch, params)
    branch_a, branch_a_second, _ = apply_action(branch_a, second_pitch, params)
    branch_b, branch_b_first, _ = apply_action(conductor, second_pitch, params)
    branch_b, branch_b_second, _ = apply_action(branch_b, first_pitch, params)
    check("conmutacion_alturas_estado", branch_a, branch_b)
    check("conmutacion_alturas_coste_ramas", branch_a_first + branch_a_second, branch_b_first + branch_b_second)
    xnc = frozenset({(0, Fraction(0), Fraction(1, 2)), (4, Fraction(1, 2), Fraction(1))})
    t = Action("ins", (9, Fraction(-1), Fraction(0)))
    u = Action("ins", (11, Fraction(1), Fraction(2)))
    xt, _, _ = apply_action(xnc, t, params)
    xtu, _, _ = apply_action(xt, u, params)
    xu, _, _ = apply_action(xnc, u, params)
    xut, _, _ = apply_action(xu, t, params)
    check("no_conmutatividad_estructural", xtu == xut, False)
    b1 = frozenset({(7, Fraction(0), Fraction(1, 7)), (7, Fraction(1, 7), Fraction(2, 7)),
                    (7, Fraction(2, 7), Fraction(3, 7)), (3, Fraction(3, 7), Fraction(1))})
    b2 = frozenset({(5, Fraction(0), Fraction(1, 7)), (5, Fraction(1, 7), Fraction(2, 7)),
                    (5, Fraction(2, 7), Fraction(3, 7)), (2, Fraction(3, 7), Fraction(1))})
    check("beethoven_D_gamma", Fraction(compare_states(b1, b2, params)["distance"]["exact"]), Fraction(91, 12))
    beethoven_actions = [Action("h", event, -2) for event in sorted(b1) if event[0] == 7] + [Action("h", (3, Fraction(3, 7), Fraction(1)), -1)]
    check("beethoven_coste_trayectoria", Fraction(evaluate_actions(b1, beethoven_actions, params)["cost"]["exact"]), Fraction(91, 12))
    deleted_state, deleted_cost, _ = apply_action(b1, Action("del", (7, Fraction(1, 7), Fraction(2, 7))), params)
    check("cardinalidad_eliminacion", deleted_cost, Fraction(5))
    check("cardinalidad_D_gamma", Fraction(compare_states(b1, deleted_state, params)["distance"]["exact"]), Fraction(5))
    divergence = frozenset({(0, Fraction(0), Fraction(1)), (120, Fraction(1, 8), Fraction(1, 4))})
    dpost, dcost, _ = apply_action(divergence, Action("u", (0, Fraction(0), Fraction(1)), Fraction(-1, 8)), params)
    check("divergencia_estado", (120, Fraction(2, 9), Fraction(1, 3)) in dpost, True)
    check("divergencia_coste_trayectoria", dcost, Fraction(1, 8))
    check("divergencia_D_gamma", Fraction(compare_states(divergence, dpost, params)["distance"]["exact"]), Fraction(13, 72))
    singleton = frozenset({(0, Fraction(0), Fraction(1))})
    compactness_ok = True
    for n in (1, 12, 120):
        z_n = (n, Fraction(0), Fraction(1))
        inserted_n, first_cost, _ = apply_action(singleton, Action("ins", z_n), params)
        restored_n, second_cost, _ = apply_action(inserted_n, Action("del", z_n), params)
        compactness_ok = compactness_ok and restored_n == singleton and first_cost + second_cost == 2 * params["gamma"]
    check("familia_no_compacta_horizonte_2", compactness_ok, True)
    return {"status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL", "cases": cases,
            "note": "Fixtures ejecutadas con aritmética racional exacta."}


def reversible_fixture(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fixture mínima reversible controlada (requisitos 3 y 12).

    Construye dos estados X e Y con X --pitch(+1)--> Y y Y --pitch(-1)--> X
    sobre un evento de altura, sin forzar aristas inversas. Luego ejecuta
    search_request en modo DECLARED_GRID para demostrar que la materialización
    de aristas es completa y que X e Y caen en la misma SCC no trivial.
    """
    params = {"omega_pc": 1, "omega_lin": 1, "omega_on": 1, "omega_off": 1, "gamma": 5}
    X = frozenset({(0, Fraction(0), Fraction(1, 2)), (4, Fraction(1, 2), Fraction(1))})
    ev = (0, Fraction(0), Fraction(1, 2))
    checks: list[dict[str, Any]] = []

    def check(name: str, obtained: Any, expected: Any) -> None:
        checks.append({
            "name": name,
            "status": "PASS" if obtained == expected else "FAIL",
            "expected": str(expected),
            "obtained": str(obtained),
        })

    # Roundtrip directo de pitch (sin normalización, reversible exacto).
    Y, _, rec_fwd = apply_action(X, Action("h", ev, 1), params)
    X2, _, rec_bwd = apply_action(Y, Action("h", (1, Fraction(0), Fraction(1, 2)), -1), params)

    check("pitch_plus1_admissible_in_X", rec_fwd["admissible"], True)
    check("pitch_minus1_admissible_in_Y", rec_bwd["admissible"], True)
    check("apply_pitch_plus1_X_canonicalizes_to_Y", state_id(Y), state_id(frozenset({(1, Fraction(0), Fraction(1, 2)), (4, Fraction(1, 2), Fraction(1))})))
    check("apply_pitch_minus1_Y_canonicalizes_to_X", state_id(X2), state_id(X))
    check("reverse_result_state_id_matches_source", state_id(X2), state_id(X))

    # Grafo operacional materializado sobre la fixture (DECLARED_GRID).
    resp = search_request({
        "source": _pl_state(X),
        "target": _pl_state(Y),
        "mode": "DECLARED_GRID",
        "parameters": params,
        "envelope": {
            "max_steps": 3, "max_nodes": 300, "timeout_ms": 4000,
            "pitch_deltas": [-1, 1], "time_deltas": [], "insertions": [],
        },
    })
    edges = resp["explored_graph"]["edges"]
    dir_set = {(e["source"], e["target"]) for e in edges}
    sid_x, sid_y = state_id(X), state_id(Y)

    check("E_R_contains_X_to_Y", (sid_x, sid_y) in dir_set, True)
    check("E_R_contains_Y_to_X", (sid_y, sid_x) in dir_set, True)
    check("X_and_Y_in_same_SCC", (sid_x in resp["graph_scc_statistics"]["largest_scc_state_ids"] and sid_y in resp["graph_scc_statistics"]["largest_scc_state_ids"]), True)
    check("largest_scc_cardinality_ge_2", resp["graph_scc_statistics"]["largest_scc_cardinality"] >= 2, True)

    fixture_reversible_passed = all(c["status"] == "PASS" for c in checks)
    return {
        "fixture_reversible_passed": fixture_reversible_passed,
        "edge_materialization_complete": resp["edge_materialization_complete"],
        "edge_materialization_source_count": resp["edge_materialization_source_count"],
        "node_count": resp["discovered_node_count"],
        "largest_scc_cardinality": resp["graph_scc_statistics"]["largest_scc_cardinality"],
        "nontrivial_scc_count": resp["graph_scc_statistics"]["nontrivial_scc_count"],
        "graph_status": resp["graph_status"],
        "source_state_id": sid_x,
        "target_state_id": sid_y,
        "checks": checks,
    }


def _pl_state(state: State) -> dict[str, Any]:
    """Helper local: state -> payload JSON."""
    return {"events": [[h, str(u), str(v)] for h, u, v in sorted(state)]}
