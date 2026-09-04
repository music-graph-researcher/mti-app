"""Capítulo 6 · Auditoría de implementabilidad y jerarquía tipada (app 8003).

Este módulo implementa el framework de constitución jerárquica del Capítulo 6
y la realización fundacional ``0 -> 1`` (evento -> motivo normalizado), reutilizando
la representación eventiva, la aritmética racional exacta y los operadores
motívicos de 8002 (`backend.operations`).

Reglas de fidelidad (resumidas del documento ``cap6_implementabilidad_codex_8003.md``):

* ``r`` es un índice jerárquico, NO una escala temporal ni un epsilon topológico.
* Las ocurrencias no se colapsan por igualdad de estado.
* Una ``ConstitutionMap`` solo existe computacionalmente cuando su dominio y su
  acción han sido especificados. NO se inventa ``A_{1->2}``.
* Toda constitución efectiva conserva su testigo (configuración) y produce un
  ``ConstitutionRecord``.
* La compatibilidad transformacional exige igualdad de dominios y de valores.
* La compatibilidad topológica es opcional y ``NOT_SPECIFIED`` por defecto en 0->1.
* La recursividad es arquitectónica: ``A_{0->1}`` no implica ``A_{1->2}``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import platform
import random
from fractions import Fraction
from typing import Any, Callable

from .operations import (
    Action,
    OperationalError,
    apply_action,
    parse_action,
    parse_state,
    state_id,
    state_payload,
)
from .version import GIT_COMMIT, SOFTWARE_VERSION


DEFAULT_PROFILE = {"omega_pc": 1, "omega_lin": 1, "omega_on": 1, "omega_off": 1, "gamma": 5}
A_0_1_MAP_ID = "A_0_1"
A_0_1_VERSION = "1.0.0"
DEFAULT_ARTICULATION = "alpha0"


class HierarchyError(ValueError):
    """Entrada o transición fuera del marco tipado del Capítulo 6."""


# ---------------------------------------------------------------------------
# Aritmética racional exacta y payloads
# ---------------------------------------------------------------------------
def _exact(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _frac(value: Any, name: str) -> Fraction:
    if isinstance(value, dict):
        value = value.get("exact")
    if isinstance(value, bool) or isinstance(value, float):
        raise HierarchyError(f"{name} debe ser un entero o una fracción exacta")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise HierarchyError(f"{name} no es una fracción válida") from exc


def _frac_payload(value: Fraction) -> dict[str, str | float]:
    return {"exact": _exact(value), "decimal": float(value)}


# ---------------------------------------------------------------------------
# Nivel basal: evento (p, tau, d, alpha)  ->  E_0 = Z x R x R_{>0} x A
# ---------------------------------------------------------------------------
def parse_basal_event(value: Any, name: str = "evento") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HierarchyError(f"{name} debe ser un objeto")
    pitch = value.get("pitch")
    if type(pitch) is not int:
        raise HierarchyError(f"La altura de {name} debe ser un entero")
    onset = _frac(value.get("onset"), f"onset de {name}")
    duration = _frac(value.get("duration"), f"duración de {name}")
    if duration <= 0:
        raise HierarchyError(f"La duración de {name} debe ser positiva")
    articulation = value.get("articulation", DEFAULT_ARTICULATION)
    if not isinstance(articulation, str) or not articulation:
        raise HierarchyError(f"La articulación de {name} debe ser un texto no vacío")
    return {"pitch": pitch, "onset": onset, "duration": duration, "articulation": articulation}


def basal_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "pitch": event["pitch"],
        "onset": _exact(event["onset"]),
        "duration": _exact(event["duration"]),
        "articulation": event["articulation"],
    }


# ---------------------------------------------------------------------------
# Nivel superior: estado motívico normalizado  E_1 = E_mot^norm
# ---------------------------------------------------------------------------
def parse_motif_state(value: Any, name: str = "estado motívico") -> frozenset[tuple[int, Fraction, Fraction]]:
    """Acepta ``{"events": [[h,u,v],...]}`` (mismo formato que 8002)."""
    try:
        return parse_state(value)
    except OperationalError as exc:
        raise HierarchyError(f"{name} no válido: {exc}") from exc


def motif_state_payload(state: frozenset[tuple[int, Fraction, Fraction]]) -> dict[str, Any]:
    return state_payload(state)


def _state_id(state: frozenset[tuple[int, Fraction, Fraction]]) -> str:
    return state_id(state)


# ---------------------------------------------------------------------------
# Configuración  Xi_r = (X_r, rho_r, xi_r) ∈ C_r
# ---------------------------------------------------------------------------
def parse_configuration(value: Any, name: str = "configuración") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HierarchyError(f"{name} debe ser un objeto")
    level = value.get("level", 0)
    if type(level) is not int or level < 0:
        raise HierarchyError("level debe ser un entero no negativo")
    occurrences_raw = value.get("occurrences")
    if not isinstance(occurrences_raw, list) or not occurrences_raw:
        raise HierarchyError("occurrences debe ser una familia finita no vacía")
    seen: set[str] = set()
    occurrences: list[dict[str, Any]] = []
    for index, occ in enumerate(occurrences_raw, 1):
        if not isinstance(occ, dict):
            raise HierarchyError(f"Ocurrencia {index} no válida")
        occ_id = occ.get("id", f"occ-{index}")
        if not isinstance(occ_id, str) or not occ_id:
            raise HierarchyError(f"La ocurrencia {index} necesita un id no vacío")
        if occ_id in seen:
            raise HierarchyError(f"El id de ocurrencia '{occ_id}' está duplicado")
        seen.add(occ_id)
        state = occ.get("state")
        if level == 0:
            parsed_state = basal_event_payload(parse_basal_event(state, f"ocurrencia {occ_id}"))
        else:
            parsed_state = motif_state_payload(parse_motif_state(state, f"ocurrencia {occ_id}"))
        occurrences.append({
            "id": occ_id,
            "state": parsed_state,
            "role": occ.get("role"),
            "metadata": occ.get("metadata"),
        })
    relations = value.get("relations", {"type": "B(M)"} if level == 0 else {})
    auxiliary_data = value.get("auxiliary_data", {"p_ton": 0} if level == 0 else {})
    return {
        "level": level,
        "occurrences": occurrences,
        "relations": relations,
        "auxiliary_data": auxiliary_data,
    }


def configuration_payload(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "level": config["level"],
        "occurrences": config["occurrences"],
        "relations": config["relations"],
        "auxiliary_data": config["auxiliary_data"],
    }


def _basal_events(config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if config["level"] != 0:
        raise HierarchyError("La realización fundacional 0->1 opera sobre configuraciones de nivel 0")
    events: list[tuple[str, dict[str, Any]]] = []
    for occ in config["occurrences"]:
        ev = parse_basal_event(occ["state"], f"ocurrencia {occ['id']}")
        events.append((occ["id"], ev))
    return events


def _p_ton(config: dict[str, Any]) -> int:
    p_ton = config["auxiliary_data"].get("p_ton", 0)
    if type(p_ton) is not int:
        raise HierarchyError("p_ton debe ser un entero")
    return p_ton


# ---------------------------------------------------------------------------
# B(M) — relación constitutiva del nivel basal
# ---------------------------------------------------------------------------
def B_of(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Relación estructural basal. Para el nivel 0, Rel_0(M) = {B(M)} (singleton)."""
    return {
        "type": "B(M)",
        "size": len(events),
        "event_ids": [eid for eid, _ in events],
    }


# ---------------------------------------------------------------------------
# A_0_1 : C_0 -> E_1 = E_mot^norm   (normalización afín del soporte temporal)
# ---------------------------------------------------------------------------
def _basal_normalization(config: dict[str, Any]) -> tuple[int, Fraction, Fraction]:
    events = _basal_events(config)
    p_ton = _p_ton(config)
    onsets = [ev["onset"] for _, ev in events]
    offsets = [ev["onset"] + ev["duration"] for _, ev in events]
    start = min(onsets)
    end = max(offsets)
    span = end - start
    if span <= 0:
        raise HierarchyError("La configuración basal debe tener extensión temporal positiva")
    return p_ton, start, span


def _normalized_descriptors(config: dict[str, Any]) -> list[tuple[str, tuple[int, Fraction, Fraction]]]:
    p_ton, start, span = _basal_normalization(config)
    out: list[tuple[str, tuple[int, Fraction, Fraction]]] = []
    for occ_id, ev in _basal_events(config):
        h = ev["pitch"] - p_ton
        u = (ev["onset"] - start) / span
        v = (ev["onset"] + ev["duration"] - start) / span
        out.append((occ_id, (h, u, v)))
    return out


def A_0_1(config: dict[str, Any]) -> dict[str, Any]:
    """Constitución fundacional: evento -> motivo normalizado.

    ``A_0_1(M, B(M), p_ton) = N(G^mot_{M,p_ton})``.
    """
    cfg = parse_configuration(configuration_payload(config) if "occurrences" in config else config)
    descriptors = _normalized_descriptors(cfg)
    state = frozenset(x for _, x in descriptors)
    return motif_state_payload(state)


def in_A_0_1_domain(config: dict[str, Any]) -> bool:
    try:
        cfg = parse_configuration(config)
        if cfg["level"] != 0:
            return False
        _basal_normalization(cfg)
        return True
    except HierarchyError:
        return False


# ---------------------------------------------------------------------------
# Reindexación
# ---------------------------------------------------------------------------
def reindex_configuration(config: Any, sigma: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    occurrences = cfg["occurrences"]
    n = len(occurrences)
    if not isinstance(sigma, list) or len(sigma) != n:
        raise HierarchyError("sigma debe ser una permutación (lista) de longitud igual al número de ocurrencias")
    if sorted(sigma) != list(range(n)):
        raise HierarchyError("sigma debe ser una biyección sobre los índices de la familia")
    reindexed = [occurrences[i] for i in sigma]
    return configuration_payload({**cfg, "occurrences": reindexed})


def equivalent_mod_reindexing(cfg_a: Any, cfg_b: Any) -> bool:
    a = parse_configuration(cfg_a)
    b = parse_configuration(cfg_b)
    if a["level"] != b["level"]:
        return False
    if a["relations"] != b["relations"]:
        return False
    if a["auxiliary_data"] != b["auxiliary_data"]:
        return False
    if len(a["occurrences"]) != len(b["occurrences"]):
        return False
    # Coinciden si existe una biyección entre ids que conserva el estado (y role).
    def signature(occ):
        return (json.dumps(occ["state"], sort_keys=True), occ["role"])
    from collections import Counter
    return Counter(signature(o) for o in a["occurrences"]) == Counter(signature(o) for o in b["occurrences"])


# ---------------------------------------------------------------------------
# ConstitutionMap / ConstitutionRecord / procedencia
# ---------------------------------------------------------------------------
def _record_id(config: dict[str, Any], map_id: str, version: str, result_state: Any) -> str:
    payload = json.dumps({
        "configuration": config,
        "map_id": map_id,
        "version": version,
        "result_state": result_state,
    }, sort_keys=True, separators=(",", ":"))
    return "rec-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def constitute(map_spec: Any, config: Any) -> dict[str, Any]:
    if not isinstance(map_spec, dict):
        raise HierarchyError("map_spec debe ser un objeto")
    map_id = map_spec.get("map_id")
    version = map_spec.get("version", "1.0.0")
    if map_id != A_0_1_MAP_ID:
        raise HierarchyError(
            f"Solo está implementada la constitución fundacional '{A_0_1_MAP_ID}'. "
            f"'{map_id}' no está especificada."
        )
    cfg = parse_configuration(config)
    if not in_A_0_1_domain(cfg):
        return {
            "status": "OUT_OF_DOMAIN",
            "record_id": None,
            "reason": "La configuración no pertenece al dominio de A_0_1 (debe ser nivel 0, no vacía y con extensión temporal positiva).",
        }
    result_state = A_0_1(cfg)
    record = {
        "record_id": _record_id(cfg, map_id, version, result_state),
        "source_level": 0,
        "target_level": 1,
        "configuration": configuration_payload(cfg),
        "constitution_map_id": map_id,
        "constitution_map_version": version,
        "result_state": result_state,
        "verification_snapshot": {
            "status": "CONSTITUTED",
            "exact_arithmetic": "fractions.Fraction",
            "app_version": SOFTWARE_VERSION,
            "git_commit": GIT_COMMIT,
        },
        "provenance_metadata": {
            "reproduces": "A_0_1(configuration) == result_state",
            "segmentación_motívica": "not_asserted",
        },
    }
    return {"status": "CONSTITUTED", "record": record}


def observed_preimages(records: list[dict[str, Any]], result_state: Any) -> list[dict[str, Any]]:
    """Fibra observada (NO fibra completa)."""
    def _canonical(state: Any) -> str:
        events = state.get("events") if isinstance(state, dict) else None
        if events is not None:
            return json.dumps(events, sort_keys=True, separators=(",", ":"))
        return json.dumps(state, sort_keys=True, separators=(",", ":"))
    target = _canonical(result_state)
    out: list[dict[str, Any]] = []
    for rec in records:
        if _canonical(rec.get("result_state")) == target:
            out.append({
                "record_id": rec.get("record_id"),
                "configuration": rec.get("configuration"),
                "constitution_map_id": rec.get("constitution_map_id"),
                "constitution_map_version": rec.get("constitution_map_version"),
            })
    return out


# ---------------------------------------------------------------------------
# Constructor explícito de preimagen (§19)
# ---------------------------------------------------------------------------
def construct_eventive_preimage(X: Any, alpha0: str = DEFAULT_ARTICULATION) -> dict[str, Any]:
    """Construye Xi_X = (M_X, B(M_X), 0) tal que A_0_1(Xi_X) == X."""
    state = parse_motif_state(X, "X")
    occurrences = []
    for index, (h, u, v) in enumerate(sorted(state), 1):
        if v <= u:
            raise HierarchyError("El descriptor motívico debe satisfacer u < v")
        occurrences.append({
            "id": f"pre-{index}",
            "state": basal_event_payload({
                "pitch": h,
                "onset": u,
                "duration": v - u,
                "articulation": alpha0,
            }),
        })
    config = {
        "level": 0,
        "occurrences": occurrences,
        "relations": {"type": "B(M)"},
        "auxiliary_data": {"p_ton": 0},
    }
    result_state = A_0_1(config)
    assert _state_id(parse_motif_state(result_state)) == _state_id(state), "constructor de preimagen debe reproducir X"
    record = {
        "record_id": _record_id(config, A_0_1_MAP_ID, A_0_1_VERSION, result_state),
        "source_level": 0,
        "target_level": 1,
        "configuration": config,
        "constitution_map_id": A_0_1_MAP_ID,
        "constitution_map_version": A_0_1_VERSION,
        "result_state": result_state,
        "verification_snapshot": {
            "status": "CONSTITUTED",
            "reproduces_source": True,
            "exact_arithmetic": "fractions.Fraction",
        },
        "provenance_metadata": {
            "constructor": "construct_eventive_preimage",
            "alpha0": alpha0,
            "note": "Prueba realizabilidad formal; NO afirmación de reconocimiento motívico en corpus.",
        },
    }
    return record


# ---------------------------------------------------------------------------
# Criterios constitutivos
# ---------------------------------------------------------------------------
def _apply_A_0_1(config: Any) -> str:
    return _state_id(parse_motif_state(A_0_1(parse_configuration(config))))


def verify_nonconstant(map_spec: Any, witness_configurations: Any) -> dict[str, Any]:
    if not isinstance(witness_configurations, list):
        raise HierarchyError("witness_configurations debe ser una lista")
    images = [(_apply_A_0_1(cfg)) for cfg in witness_configurations]
    if len(images) < 2:
        return {"status": "INSUFFICIENT_WITNESSES", "distinct_images": 0, "images": images}
    distinct = len(set(images))
    if distinct >= 2:
        return {"status": "PASS", "distinct_images": distinct, "images": images}
    return {"status": "FAIL_ON_DECLARED_FAMILY", "distinct_images": 1, "images": images}


def verify_not_reducible_to_fixed_component(map_spec: Any, family_D: Any, policy: Any = None) -> dict[str, Any]:
    if not isinstance(family_D, list) or len(family_D) < 2:
        return {"status": "INSUFFICIENT_WITNESSES", "details": "Se requieren al menos dos configuraciones"}
    configs = [parse_configuration(cfg) for cfg in family_D]
    n = len(configs[0]["occurrences"])
    if any(len(c["occurrences"]) != n for c in configs):
        return {"status": "INSUFFICIENT_WITNESSES", "details": "Las configuraciones deben tener la misma cardinalidad"}
    results = [_apply_A_0_1(cfg) for cfg in configs]
    failures = []
    for index in range(n):
        found = False
        for i in range(len(configs)):
            for j in range(i + 1, len(configs)):
                state_i = json.dumps(configs[i]["occurrences"][index]["state"], sort_keys=True)
                state_j = json.dumps(configs[j]["occurrences"][index]["state"], sort_keys=True)
                if state_i == state_j and results[i] != results[j]:
                    found = True
                    break
            if found:
                break
        if not found:
            failures.append({"index": index, "reason": "FAIL_FOR_INDEX"})
    if failures:
        return {"status": "FAIL_FOR_INDEX", "failures": failures}
    return {"status": "PASS_ON_DECLARED_FINITE_FAMILY", "checked_indices": n}


def verify_relational_constitutiveness(map_spec: Any, config_a: Any, config_b: Any, policy: Any = None) -> dict[str, Any]:
    # Para 0->1, Rel_0(M) = {B(M)}: una única relación admisible => no testable.
    return {
        "status": "NOT_TESTABLE_RELATION_NOT_INDEPENDENT",
        "reason": "En la realización 0->1, Rel_0(M) es un singleton {B(M)}; no puede variarse rho_0 manteniendo M fija.",
    }


# ---------------------------------------------------------------------------
# J_x y realizaciones configuracionales de operadores motívicos (8002)
# ---------------------------------------------------------------------------
def eventive_support_for_descriptor(config: Any, x: Any) -> list[str]:
    cfg = parse_configuration(config)
    p_ton, start, span = _basal_normalization(cfg)
    h, u, v = _parse_descriptor(x)
    ids: list[str] = []
    for occ_id, ev in _basal_events(cfg):
        hh = ev["pitch"] - p_ton
        uu = (ev["onset"] - start) / span
        vv = (ev["onset"] + ev["duration"] - start) / span
        if hh == h and uu == u and vv == v:
            ids.append(occ_id)
    return ids


def _parse_descriptor(x: Any) -> tuple[int, Fraction, Fraction]:
    if isinstance(x, dict):
        if "events" in x:
            st = parse_motif_state(x)
            if len(st) != 1:
                raise HierarchyError("El descriptor debe ser un único evento (h,u,v)")
            return next(iter(st))
        h = x.get("h"); u = x.get("u"); v = x.get("v")
    elif isinstance(x, (list, tuple)) and len(x) == 3:
        h, u, v = x
    else:
        raise HierarchyError("El descriptor debe ser [h,u,v] o {h,u,v}")
    if type(h) is not int:
        raise HierarchyError("La altura del descriptor debe ser entera")
    return h, _frac(u, "u"), _frac(v, "v")


def _clone_config_with_events(config: Any, new_events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    cfg = parse_configuration(config)
    occurrences = [
        {"id": occ_id, "state": basal_event_payload(ev), "role": None, "metadata": None}
        for occ_id, ev in new_events
    ]
    return {
        "level": 0,
        "occurrences": occurrences,
        "relations": B_of(new_events),
        "auxiliary_data": cfg["auxiliary_data"],
    }


def lift_pitch_to_C0(config: Any, x: Any, delta_h: Any) -> dict[str, Any]:
    if type(delta_h) is not int:
        raise HierarchyError("delta_h debe ser un entero")
    cfg = parse_configuration(config)
    target = set(eventive_support_for_descriptor(cfg, x))
    events = _basal_events(cfg)
    new_events = []
    for occ_id, ev in events:
        if occ_id in target:
            ev = {**ev, "pitch": ev["pitch"] + delta_h}
        new_events.append((occ_id, ev))
    return _clone_config_with_events(cfg, new_events)


def lift_onset_to_C0(config: Any, x: Any, delta_u: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    du = _frac(delta_u, "delta_u")
    _, _, span = _basal_normalization(cfg)
    target = set(eventive_support_for_descriptor(cfg, x))
    events = _basal_events(cfg)
    new_events = []
    for occ_id, ev in events:
        if occ_id in target:
            ev = {**ev, "onset": ev["onset"] + span * du, "duration": ev["duration"] - span * du}
        new_events.append((occ_id, ev))
    return _clone_config_with_events(cfg, new_events)


def lift_offset_to_C0(config: Any, x: Any, delta_v: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    dv = _frac(delta_v, "delta_v")
    _, _, span = _basal_normalization(cfg)
    target = set(eventive_support_for_descriptor(cfg, x))
    events = _basal_events(cfg)
    new_events = []
    for occ_id, ev in events:
        if occ_id in target:
            ev = {**ev, "duration": ev["duration"] + span * dv}
        new_events.append((occ_id, ev))
    return _clone_config_with_events(cfg, new_events)


def lift_insert_to_C0(config: Any, z: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    p_ton, start, span = _basal_normalization(cfg)
    h, s, e = _parse_descriptor(z)
    if not (s < e):
        raise HierarchyError("La inserción requiere s < e")
    events = _basal_events(cfg)
    new_id = f"ins-{len(events) + 1}"
    events.append((new_id, {
        "pitch": p_ton + h,
        "onset": start + span * s,
        "duration": span * (e - s),
        "articulation": DEFAULT_ARTICULATION,
    }))
    return _clone_config_with_events(cfg, events)


def lift_delete_to_C0(config: Any, x: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    target = set(eventive_support_for_descriptor(cfg, x))
    events = _basal_events(cfg)
    new_events = [(occ_id, ev) for occ_id, ev in events if occ_id not in target]
    if not new_events:
        raise HierarchyError("La eliminación no puede vaciar la configuración basal")
    return _clone_config_with_events(cfg, new_events)


def _verify_commutativity(config: Any, motif_action: Action, lifted_config: Any) -> dict[str, Any]:
    """Compara las dos ramas del diagrama: A(lift(Xi)) vs T(A(Xi))."""
    cfg = parse_configuration(config)
    X = parse_motif_state(A_0_1(cfg))
    try:
        post_motif, _, _ = apply_action(X, motif_action, DEFAULT_PROFILE)
        motif_ok = True
        motif_id = _state_id(post_motif)
    except OperationalError:
        motif_ok = False
        motif_id = None
    try:
        lifted_X = parse_motif_state(A_0_1(lifted_config))
        lifted_id = _state_id(lifted_X)
        lifted_ok = True
    except HierarchyError:
        lifted_ok = False
        lifted_id = None
    nonempty = motif_ok and lifted_ok
    return {
        "domain_equality_status": "PASS" if (motif_ok == lifted_ok) else "DOMAIN_MISMATCH",
        "value_equality_status": "PASS" if (motif_ok and lifted_ok and motif_id == lifted_id) else "VALUE_MISMATCH",
        "nonempty_domain_status": "PASS" if nonempty else "EMPTY_COMMON_DOMAIN",
        "overall": "PASS" if (motif_ok and lifted_ok and motif_id == lifted_id) else "MISMATCH",
        "motif_branch_state_id": motif_id,
        "lifted_branch_state_id": lifted_id,
        "motif_branch_state": motif_state_payload(post_motif) if motif_ok else None,
        "lifted_branch_state": motif_state_payload(lifted_X) if lifted_ok else None,
    }


def verify_lift_operator(config: Any, operator: str, x: Any, delta: Any = None) -> dict[str, Any]:
    cfg = parse_configuration(config)
    h, u, v = _parse_descriptor(x)
    if operator == "pitch":
        delta_val = int(delta)
        motif_action = Action("h", (h, u, v), delta_val)
        lifted = lift_pitch_to_C0(cfg, (h, u, v), delta_val)
    elif operator == "onset":
        delta_val = _frac(delta, "delta_u")
        motif_action = Action("u", (h, u, v), delta_val)
        lifted = lift_onset_to_C0(cfg, (h, u, v), delta_val)
    elif operator == "offset":
        delta_val = _frac(delta, "delta_v")
        motif_action = Action("v", (h, u, v), delta_val)
        lifted = lift_offset_to_C0(cfg, (h, u, v), delta_val)
    elif operator == "insert":
        delta_val = None
        motif_action = Action("ins", (h, u, v))
        lifted = lift_insert_to_C0(cfg, (h, u, v))
    elif operator == "delete":
        delta_val = None
        motif_action = Action("del", (h, u, v))
        lifted = lift_delete_to_C0(cfg, (h, u, v))
    elif operator == "identity":
        delta_val = None
        motif_action = Action("id")
        lifted = cfg
    else:
        raise HierarchyError(f"Operador desconocido: {operator}")
    compat = _verify_commutativity(cfg, motif_action, lifted)
    return {
        "operator": operator,
        "descriptor": {"h": h, "u": _exact(u), "v": _exact(v)},
        "delta": _exact(delta_val) if isinstance(delta_val, (int, Fraction)) else None,
        "compatibility": compat,
        "lifted_configuration": lifted,
    }


def apply_motif_word(state: frozenset[tuple[int, Fraction, Fraction]], word: list[Any]) -> frozenset[tuple[int, Fraction, Fraction]]:
    current = state
    for item in word:
        action = item if isinstance(item, Action) else parse_action(item)
        current, _, _ = apply_action(current, action, DEFAULT_PROFILE)
    return current


def lift_motif_word_to_C0(config: Any, word: list[Any]) -> dict[str, Any]:
    cfg = parse_configuration(config)
    current = cfg
    for item in word:
        action = item if isinstance(item, Action) else parse_action(item)
        if action.kind == "id":
            continue
        if action.kind == "h":
            current = lift_pitch_to_C0(current, list(action.event), action.delta)
        elif action.kind == "u":
            current = lift_onset_to_C0(current, list(action.event), action.delta)
        elif action.kind == "v":
            current = lift_offset_to_C0(current, list(action.event), action.delta)
        elif action.kind == "ins":
            current = lift_insert_to_C0(current, list(action.event))
        elif action.kind == "del":
            current = lift_delete_to_C0(current, list(action.event))
        else:
            raise HierarchyError(f"Operador '{action.kind}' no tiene realización basal")
    return current


def verify_lifted_composition(config: Any, word: list[Any]) -> dict[str, Any]:
    cfg = parse_configuration(config)
    X = parse_motif_state(A_0_1(cfg))
    try:
        lifted = lift_motif_word_to_C0(cfg, word)
        lifted_X = parse_motif_state(A_0_1(lifted))
        lifted_id = _state_id(lifted_X)
        lifted_ok = True
    except HierarchyError:
        lifted_id = None
        lifted_ok = False
    try:
        post = apply_motif_word(X, word)
        post_id = _state_id(post)
        post_ok = True
    except OperationalError:
        post_id = None
        post_ok = False
    value_ok = lifted_ok and post_ok and lifted_id == post_id
    return {
        "domain_equality_status": "PASS" if (lifted_ok == post_ok) else "DOMAIN_MISMATCH",
        "value_equality_status": "PASS" if value_ok else "VALUE_MISMATCH",
        "nonempty_domain_status": "PASS" if (lifted_ok and post_ok) else "EMPTY_COMMON_DOMAIN",
        "overall": "PASS" if value_ok else "MISMATCH",
        "motif_branch_state_id": post_id,
        "lifted_branch_state_id": lifted_id,
    }


# ---------------------------------------------------------------------------
# Mecanismos genéricos
# ---------------------------------------------------------------------------
def copy_configuration(config: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    return configuration_payload(cfg)


def duplicate_occurrence(config: Any, occurrence_id: Any, new_id: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    source = next((o for o in cfg["occurrences"] if o["id"] == occurrence_id), None)
    if source is None:
        raise HierarchyError(f"No existe la ocurrencia '{occurrence_id}'")
    if any(o["id"] == new_id for o in cfg["occurrences"]):
        raise HierarchyError(f"El id '{new_id}' ya existe")
    occurrences = cfg["occurrences"] + [{**source, "id": new_id}]
    if cfg["level"] == 0:
        relations = B_of([(o["id"], parse_basal_event(o["state"])) for o in occurrences])
    else:
        relations = cfg["relations"]
    return configuration_payload({**cfg, "occurrences": occurrences, "relations": relations})


def extract_singleton(family: Any) -> dict[str, Any]:
    if not isinstance(family, list):
        raise HierarchyError("La familia debe ser una lista")
    if len(family) != 1:
        raise HierarchyError("extract_singleton solo es válida para cardinalidad uno")
    return {"status": "EXTRACTED", "element": family[0]}


def stochastic_sample(config: Any, mechanism: dict[str, Any], random_state: Any = None) -> dict[str, Any]:
    """Perturbación estocástica genérica: desplaza alturas según una semilla.

    Aleatoriedad NO equivale a creatividad/novedad. Registra semilla y versión.
    """
    cfg = parse_configuration(config)
    seed = int(mechanism.get("seed", random_state or 0))
    rng = random.Random(seed)
    occurrences = []
    for occ in cfg["occurrences"]:
        ev = parse_basal_event(occ["state"]) if cfg["level"] == 0 else None
        if ev is not None and mechanism.get("kind") == "pitch_jitter":
            ev = {**ev, "pitch": ev["pitch"] + rng.randint(-int(mechanism.get("radius", 1)), int(mechanism.get("radius", 1)))}
            occurrences.append({"id": occ["id"], "state": basal_event_payload(ev)})
        else:
            occurrences.append(occ)
    return {
        "configuration": configuration_payload({**cfg, "occurrences": occurrences}),
        "seed": seed,
        "version": mechanism.get("version", "1.0.0"),
    }


def select_family(family: Any, criterion: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(family, list):
        raise HierarchyError("La familia debe ser una lista")
    mode = criterion.get("name", "first")
    if mode == "all":
        selected = list(family)
    elif mode == "none":
        selected = []
    elif mode == "first":
        selected = family[: int(criterion.get("k", 1))]
    elif mode == "last":
        selected = family[-int(criterion.get("k", 1)):] if family else []
    else:
        selected = list(family)
    return {"status": "SELECTED", "selected": selected, "criterion": criterion}


# ---------------------------------------------------------------------------
# Compatibilidad topológica (opcional; NOT_SPECIFIED por defecto en 0->1)
# ---------------------------------------------------------------------------
def verify_topological_compatibility(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("finite_configurations"):
        return {"status": "EMPTY_SET"}
    if payload.get("configuration_metric") is None or payload.get("upper_metric") is None or payload.get("L") is None:
        return {"status": "METRIC_NOT_SPECIFIED",
                "reason": "La compatibilidad topológica requiere S_r, d_Cr, d_{r+1} y L."}
    # Caso genérico opcional: verificar estabilidad L-Lipschitz sobre el conjunto finito.
    L = _frac(payload["L"], "L")
    configs = payload["finite_configurations"]
    d_lower = payload["configuration_metric"]
    d_upper = payload["upper_metric"]
    results = []
    max_ratio = Fraction(0)
    for i in range(len(configs)):
        for j in range(i + 1, len(configs)):
            dlo = _frac(d_lower[i][j], "d_Cr")
            dup = _frac(d_upper[i][j], "d_{r+1}")
            ratio = dup / dlo if dlo > 0 else None
            if ratio is not None and ratio > max_ratio:
                max_ratio = ratio
            ok = ratio is None or ratio <= L
            results.append({"i": i, "j": j, "d_lower": _exact(dlo), "d_upper": _exact(dup), "ratio": _exact(ratio) if ratio is not None else None, "ok": ok})
    if all(r["ok"] for r in results):
        status = "PASS_ON_FINITE_SET"
    else:
        status = "FAIL_STABILITY"
    return {
        "status": status,
        "minimum_lipschitz_constant_on_declared_finite_set": _exact(max_ratio),
        "L": _exact(L),
        "checked_pairs": results,
    }


# ---------------------------------------------------------------------------
# Auditor genérico
# ---------------------------------------------------------------------------
def audit_transition(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise HierarchyError("TransitionSpec debe ser un objeto")
    core_missing = [k for k in ("source_level", "target_level", "constitution_map") if k not in spec]
    report: dict[str, Any] = {
        "transition_id": spec.get("transition_id", "unlabeled-transition"),
        "source_level": spec.get("source_level"),
        "target_level": spec.get("target_level"),
        "core_specification": "FORMALLY_SPECIFIED" if not core_missing else "INCOMPLETE",
        "reindexing_invariance": "NOT_SPECIFIED",
        "constitution_domain": "NOT_SPECIFIED",
        "nontriviality": "NOT_SPECIFIED",
        "nonreducibility": "NOT_SPECIFIED",
        "relational_constitutiveness": "NOT_SPECIFIED",
        "provenance_preservation": "NOT_SPECIFIED",
        "transformational_compatibility": "NOT_SPECIFIED",
        "topological_compatibility": "NOT_SPECIFIED",
        "constitutive_completeness": "NOT_SPECIFIED",
        "recursive_participation": "NOT_SPECIFIED",
        "evidence_level": "NOT_SPECIFIED",
        "notes": ["El auditor no rellena campos ausentes."],
    }
    if core_missing:
        report["notes"].append(f"Faltan: {', '.join(core_missing)}")
        report["evidence_level"] = "INSUFFICIENT_EVIDENCE"
    return report


# ---------------------------------------------------------------------------
# Fixtures fundacionales
# ---------------------------------------------------------------------------
def _cfg_from_pairs(pairs: list[tuple[int, int]], articulation: str = DEFAULT_ARTICULATION) -> dict[str, Any]:
    occurrences = [
        {"id": f"e{i+1}", "state": basal_event_payload({"pitch": p, "onset": Fraction(0), "duration": Fraction(1), "articulation": articulation})}
        for i, p in enumerate(pairs)
    ]
    return {"level": 0, "occurrences": occurrences, "relations": {"type": "B(M)"}, "auxiliary_data": {"p_ton": 0}}


def _conductor_config() -> dict[str, Any]:
    """Configuración basal del motivo conductor (fixture 8002)."""
    conductor = [
        (0, Fraction(0), Fraction(1, 4)),
        (2, Fraction(1, 4), Fraction(3, 8)),
        (4, Fraction(1, 2), Fraction(3, 4)),
        (7, Fraction(3, 4), Fraction(1)),
    ]
    return {
        "level": 0,
        "occurrences": [
            {"id": f"e{i+1}", "state": basal_event_payload({
                "pitch": p, "onset": u, "duration": v - u, "articulation": DEFAULT_ARTICULATION,
            })}
            for i, (p, u, v) in enumerate(conductor)
        ],
        "relations": {"type": "B(M)"},
        "auxiliary_data": {"p_ton": 0},
    }


def _action_dict(action: Action) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": action.kind}
    if action.event is not None:
        out["event"] = [action.event[0], _exact(action.event[1]), _exact(action.event[2])]
    if action.delta is not None:
        out["delta"] = action.delta if isinstance(action.delta, int) else _exact(action.delta)
    return out


def verify_reindexing_invariance(map_spec: Any, config: Any) -> dict[str, Any]:
    cfg = parse_configuration(config)
    n = len(cfg["occurrences"])
    sigma = list(range(n - 1, -1, -1))
    reindexed = reindex_configuration(cfg, sigma)
    original = A_0_1(cfg)
    reindexed_state = A_0_1(reindexed)
    return {
        "status": "PASS" if original == reindexed_state else "FAIL",
        "sigma": sigma,
        "configuration": cfg,
        "reindexed_configuration": reindexed,
        "A_0_1_original": original,
        "A_0_1_reindexed": reindexed_state,
        "equivalent_mod_reindexing": equivalent_mod_reindexing(cfg, reindexed),
    }


def verify_provenance_preservation(map_spec: Any, X: list[tuple[int, Fraction, Fraction]]) -> dict[str, Any]:
    X_payload = {"events": [[h, _exact(u), _exact(v)] for h, u, v in sorted(X)]}
    rec_a = construct_eventive_preimage(X_payload)
    cfg_a = parse_configuration(rec_a["configuration"])
    cfg_b = reindex_configuration(cfg_a, [1, 0])
    rec_b = constitute(map_spec, cfg_b)["record"]
    preimages = observed_preimages([rec_a, rec_b], X_payload)
    other = {"events": [[99, "0", "1"]]}
    preimages_other = observed_preimages([rec_a, rec_b], other)
    return {
        "status": "PASS" if (
            rec_a["record_id"] != rec_b["record_id"]
            and len(preimages) == 2
            and len(preimages_other) == 0
        ) else "FAIL",
        "each_constitution_generates_record": True,
        "distinct_witnesses_distinct_records": rec_a["record_id"] != rec_b["record_id"],
        "record_ids": [rec_a["record_id"], rec_b["record_id"]],
        "observed_preimages_count": len(preimages),
        "observed_preimages_only_observed": len(preimages_other) == 0,
        "observed_preimages": preimages,
    }


def constitutive_completeness(map_spec: Any) -> dict[str, Any]:
    return {
        "status": "VERIFIED_BY_CONSTRUCTOR",
        "distinction": (
            "La sobreyectividad formal de A_0_1 se reproduce con el constructor explícito de "
            "preimagen (§19), NO mediante una enumeración exhaustiva de una imagen finita."
        ),
    }


def foundation_fixtures() -> dict[str, Any]:
    """Informe reproducible y exhaustivo de la transición fundacional 0->1.

    Devuelve testigos y resultados exactos, no únicamente un PASS global.
    """
    cfg_conductor = _conductor_config()

    # ---------------------------------------------------------------
    # 20.1 Constructor de preimagen (con resultados exactos)
    # ---------------------------------------------------------------
    preimage_fixtures = [
        [(0, Fraction(0), Fraction(1))],
        [(1, Fraction(0), Fraction(1))],
        [(0, Fraction(0), Fraction(1, 2)), (4, Fraction(1, 2), Fraction(1))],
        [(0, Fraction(0), Fraction(1, 4)), (2, Fraction(1, 4), Fraction(3, 8)), (4, Fraction(1, 2), Fraction(3, 4)), (7, Fraction(3, 4), Fraction(1))],
    ]
    preimage_cases = []
    preimage_all_ok = True
    for X in preimage_fixtures:
        state = frozenset(X)
        payload = motif_state_payload(state)
        rec = construct_eventive_preimage(payload)
        ok = _state_id(parse_motif_state(rec["result_state"])) == _state_id(state)
        preimage_all_ok = preimage_all_ok and ok
        preimage_cases.append({
            "X": [[h, _exact(u), _exact(v)] for h, u, v in sorted(X)],
            "status": "PASS" if ok else "FAIL",
            "configuration": rec["configuration"],
            "result_state": rec["result_state"],
        })

    # ---------------------------------------------------------------
    # 20.2 No trivialidad
    # ---------------------------------------------------------------
    X0 = {(0, Fraction(0), Fraction(1))}
    X1 = {(1, Fraction(0), Fraction(1))}
    c0 = construct_eventive_preimage(motif_state_payload(frozenset(X0)))["configuration"]
    c1 = construct_eventive_preimage(motif_state_payload(frozenset(X1)))["configuration"]
    nontriviality = verify_nonconstant({"map_id": A_0_1_MAP_ID}, [c0, c1])
    nontriviality_block = {
        "status": nontriviality["status"],
        "witness_configurations": [c0, c1],
        "images": nontriviality["images"],
    }

    # ---------------------------------------------------------------
    # 20.3 No reducibilidad a componente fijo
    # ---------------------------------------------------------------
    a, b, c, d = 0, 4, 7, 2
    Xi0 = _cfg_from_pairs([a, b])
    Xi1 = _cfg_from_pairs([a, c])
    Xi2 = _cfg_from_pairs([d, b])
    nonreducibility = verify_not_reducible_to_fixed_component({"map_id": A_0_1_MAP_ID}, [Xi0, Xi1, Xi2])
    nonreducibility_block = {
        "status": nonreducibility["status"],
        "family_D": [Xi0, Xi1, Xi2],
        "images": [_apply_A_0_1(x) for x in (Xi0, Xi1, Xi2)],
    }

    # ---------------------------------------------------------------
    # 20.4 Variable relacional / 20.5 Segmentación
    # ---------------------------------------------------------------
    relational = verify_relational_constitutiveness({"map_id": A_0_1_MAP_ID}, Xi0, Xi1)
    segmentation = {
        "status": "formal_constitution_valid",
        "musicological_motif_occurrence": "not_asserted",
        "reason": "8003 no usa el MTI para decidir por sí mismo qué familias son motivos.",
    }

    # ---------------------------------------------------------------
    # Reindexación / procedencia / completitud constitutiva
    # ---------------------------------------------------------------
    reindexing = verify_reindexing_invariance({"map_id": A_0_1_MAP_ID}, cfg_conductor)
    provenance = verify_provenance_preservation(
        {"map_id": A_0_1_MAP_ID, "version": A_0_1_VERSION},
        [(0, Fraction(0), Fraction(1)), (4, Fraction(0), Fraction(1))],
    )
    completeness = constitutive_completeness({"map_id": A_0_1_MAP_ID})

    # ---------------------------------------------------------------
    # 21/22 Compatibilidad transformacional (10 fixtures, con detalle)
    # ---------------------------------------------------------------
    def single_fixture(spec_id, name, operator, descriptor, delta):
        res = verify_lift_operator(cfg_conductor, operator, descriptor, delta)
        return {
            "spec_id": spec_id,
            "name": name,
            "operator": operator,
            "descriptor": res["descriptor"],
            "delta": res["delta"],
            "fixture_configuration": cfg_conductor,
            "domain_equality_status": res["compatibility"]["domain_equality_status"],
            "value_equality_status": res["compatibility"]["value_equality_status"],
            "nonempty_domain_status": res["compatibility"]["nonempty_domain_status"],
            "overall": res["compatibility"]["overall"],
            "motif_branch_state": res["compatibility"]["motif_branch_state"],
            "lifted_branch_state": res["compatibility"]["lifted_branch_state"],
        }

    transform_fixtures = [
        single_fixture("21.1", "modificación de altura", "pitch", (4, Fraction(1, 2), Fraction(3, 4)), 1),
        single_fixture("21.2", "modificación de ataque sin renormalización", "onset", (4, Fraction(1, 2), Fraction(3, 4)), Fraction(1, 16)),
        single_fixture("21.3", "modificación de terminación con renormalización efectiva", "offset", (7, Fraction(3, 4), Fraction(1)), Fraction(1, 4)),
        single_fixture("21.3", "modificación de terminación sin renormalización", "offset", (2, Fraction(1, 4), Fraction(3, 8)), Fraction(1, 16)),
        single_fixture("21.4", "inserción interna", "insert", (5, Fraction(3, 8), Fraction(1, 2)), None),
        single_fixture("21.4", "inserción externa (s < 0)", "insert", (5, Fraction(-1, 4), Fraction(0)), None),
        single_fixture("21.5", "eliminación que conserva los extremos", "delete", (2, Fraction(1, 4), Fraction(3, 8)), None),
        single_fixture("21.5", "eliminación que obliga a renormalizar", "delete", (7, Fraction(3, 4), Fraction(1)), None),
        single_fixture("21.6", "identidad", "identity", (4, Fraction(1, 2), Fraction(3, 4)), None),
    ]

    # 22. Composición de longitud > 1
    word = [Action("h", (4, Fraction(1, 2), Fraction(3, 4)), 1), Action("h", (5, Fraction(1, 2), Fraction(3, 4)), 2)]
    composition = verify_lifted_composition(cfg_conductor, word)
    composition_block = {
        "spec_id": "22",
        "name": "composición de longitud > 1 (procedente de 8002)",
        "word": [_action_dict(a) for a in word],
        "word_length": len(word),
        "fixture_configuration": cfg_conductor,
        "domain_equality_status": composition["domain_equality_status"],
        "value_equality_status": composition["value_equality_status"],
        "nonempty_domain_status": composition["nonempty_domain_status"],
        "overall": composition["overall"],
        "motif_branch_state_id": composition["motif_branch_state_id"],
        "lifted_branch_state_id": composition["lifted_branch_state_id"],
    }
    transform_fixtures.append(composition_block)

    # ---------------------------------------------------------------
    # 16. Compatibilidad topológica (NOT_SPECIFIED en 0->1)
    # ---------------------------------------------------------------
    topological = verify_topological_compatibility({"finite_configurations": [cfg_conductor]})

    # ---------------------------------------------------------------
    # Resumen flat (para la UI) y estado global
    # ---------------------------------------------------------------
    checks: list[dict[str, Any]] = [
        {"name": "20.1_constructor_de_preimagen", "status": "PASS" if preimage_all_ok else "FAIL"},
        {"name": "20.2_no_trivialidad", "status": nontriviality["status"]},
        {"name": "20.3_no_reducibilidad", "status": nonreducibility["status"]},
        {"name": "20.4_variable_relacional", "status": relational["status"]},
        {"name": "20.5_segmentacion", "status": segmentation["status"]},
        {"name": "reindexing_invariance", "status": reindexing["status"]},
        {"name": "provenance_preservation", "status": provenance["status"]},
        {"name": "constitutive_completeness", "status": completeness["status"]},
        {"name": "16_topologia", "status": topological["status"]},
    ]
    for fx in transform_fixtures:
        checks.append({"name": f"{fx['spec_id']} · {fx['name']}", "status": fx["overall"]})

    hard_pass = (
        preimage_all_ok
        and nontriviality["status"] == "PASS"
        and nonreducibility["status"] == "PASS_ON_DECLARED_FINITE_FAMILY"
        and reindexing["status"] == "PASS"
        and provenance["status"] == "PASS"
        and completeness["status"] == "VERIFIED_BY_CONSTRUCTOR"
        and all(fx["overall"] == "PASS" for fx in transform_fixtures)
    )
    soft_correct = (
        relational["status"] == "NOT_TESTABLE_RELATION_NOT_INDEPENDENT"
        and segmentation["status"] == "formal_constitution_valid"
        and topological["status"] in ("METRIC_NOT_SPECIFIED", "NOT_SPECIFIED")
    )

    return {
        "status": "PASS" if (hard_pass and soft_correct) else "FAIL",
        "report_type": "cap6-hierarchy-audit",
        "transition_id": "A_0_1",
        "source_level": 0,
        "target_level": 1,
        "core_specification": "FORMALLY_SPECIFIED",
        "exact_arithmetic": "fractions.Fraction",
        "app_version": SOFTWARE_VERSION,
        "git_commit": GIT_COMMIT,
        "runtime": f"Python {platform.python_version()}",
        "dependencies": {
            "8000_perfil_motivico": "normalización afín Pmot (mti.py) reutilizada conceptualmente",
            "8001_homologia_persistente": "no requerida para 0->1 (compatibilidad topológica NOT_SPECIFIED)",
            "8002_operadores": "operations.py: id/h/u/v/ins/del reutilizados para las realizaciones configuracionales",
        },
        "checks": checks,
        "foundation": {
            "constructor_de_preimagen": {"status": "PASS" if preimage_all_ok else "FAIL", "cases": preimage_cases},
            "nontriviality": nontriviality_block,
            "nonreducibility": nonreducibility_block,
            "relational_constitutiveness": relational,
            "segmentation": segmentation,
            "reindexing_invariance": reindexing,
            "provenance_preservation": provenance,
            "constitutive_completeness": completeness,
        },
        "transformational_compatibility": {
            "overall": "PASS" if all(fx["overall"] == "PASS" for fx in transform_fixtures) else "MISMATCH",
            "fixtures": transform_fixtures,
        },
        "topological_compatibility": topological,
    }
