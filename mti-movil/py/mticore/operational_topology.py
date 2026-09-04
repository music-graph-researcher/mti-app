"""Comparación topológica estructural--operacional sobre un único G_R finito (capítulo 5).

Toda la distancia operacional es camino mínimo DENTRO del mismo G_R materializado.
Nunca se afirma representar el ínfimo global delta_T.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import heapq
import itertools
import json
import platform
from fractions import Fraction
from typing import Any

from .operations import (
    OperationalError, State, action_payload, apply_action, compare_states,
    operational_weights, parse_action, parse_state, rational_payload, state_id, state_payload,
)
from . import ai_summaries
from .persistent_homology import PersistentHomologyError, compute_persistent_homology
from .version import GIT_COMMIT, SOFTWARE_VERSION


TOPOLOGY_STATE_LIMIT = 50

REPORT_TYPE = "cap5-topologia-validacion"
REPORT_GOAL = (
    "Certificar reproduciblemente la comparación topológica estructural-operacional "
    "sobre un subgrafo operacional finito G_R materializado. PH_R^op depende de G_R y "
    "de su política de exploración; NO constituye una estimación certificada del "
    "ínfimo global delta_T ni de la topología del sistema operacional continuo."
)


def _exact_str(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _frac_payload(value: Fraction) -> dict[str, Any]:
    return {"exact": _exact_str(value), "value": float(value)}


def _fraction(value: Any, label: str) -> Fraction:
    if isinstance(value, dict):
        value = value.get("exact")
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        raise OperationalError(f"{label} debe ser racional exacto")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise OperationalError(f"{label} no es racional exacto") from exc


def _graph(payload: Any, parameters: dict[str, Any] | None) -> tuple[dict[str, State], list[dict[str, Any]], str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        raise OperationalError("explored_graph debe contener nodes y edges")
    nodes: dict[str, State] = {}
    for index, item in enumerate(payload["nodes"]):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise OperationalError(f"Nodo {index + 1} no válido")
        state = parse_state(item.get("state"), f"nodo {item['id']}")
        if item["id"] in nodes or state_id(state) != item["id"]:
            raise OperationalError("Los identificadores de nodo deben ser canónicos y únicos")
        nodes[item["id"]] = state
    if not nodes:
        raise OperationalError("G_R no puede estar vacío")
    edges = []
    for index, raw in enumerate(payload["edges"]):
        if not isinstance(raw, dict) or raw.get("source") not in nodes or raw.get("target") not in nodes:
            raise OperationalError(f"Arista {index + 1} referencia un nodo inexistente")
        action = parse_action(raw.get("action"))
        expected = _fraction(raw.get("cost"), f"coste de arista {index + 1}")
        if expected < 0:
            raise OperationalError("G_R no admite costes negativos")
        try:
            after, cost, transition = apply_action(nodes[raw["source"]], action, parameters)
        except OperationalError as exc:
            raise OperationalError(f"Arista {index + 1} no reproducible: {exc}") from exc
        if state_id(after) != raw["target"] or cost != expected:
            raise OperationalError(f"Arista {index + 1} no coincide con la transición operacional reproducida")
        norm_info = transition.get("normalization")
        norm_effective = bool(norm_info and norm_info.get("effective"))
        canon_inert = bool(transition.get("canonically_inert"))
        edges.append({
            "edge_id": f"e-{index + 1}",
            "source_state_id": raw["source"],
            "target_state_id": raw["target"],
            "action": action_payload(action),
            "cost": rational_payload(cost),
            "canonically_inert": canon_inert,
            "normalization_effective": norm_effective,
            "transition_record": transition,
        })
    edges.sort(key=lambda edge: (edge["source_state_id"], edge["target_state_id"], json.dumps(edge["action"], sort_keys=True), edge["cost"]["exact"]))
    for index, edge in enumerate(edges, 1):
        edge["edge_id"] = f"e-{index}"
        edge["transition_ref"] = edge["edge_id"]
    canonical_nodes = [{"id": identifier, "state": state_payload(nodes[identifier])} for identifier in sorted(nodes)]
    canonical_edges = [
        {key: edge[key] for key in ("source_state_id", "target_state_id", "action", "cost")}
        for edge in edges
    ]
    canonical_edges.sort(key=lambda edge: json.dumps(edge, sort_keys=True, separators=(",", ":")))
    canonical = {"nodes": canonical_nodes, "edges": canonical_edges}
    graph_id = "gr-" + hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    return nodes, edges, graph_id


def _weighted_adjacency(nodes: dict[str, State], edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    weighted = {node: [] for node in nodes}
    for edge in edges:
        weighted[edge["source_state_id"]].append(edge)
    for node in nodes:
        weighted[node].sort(key=lambda e: (e["target_state_id"], json.dumps(e["action"], sort_keys=True)))
    return weighted


def _plain_adjacency(nodes: dict[str, State], edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    plain = {node: [] for node in nodes}
    for edge in edges:
        plain[edge["source_state_id"]].append(edge["target_state_id"])
    for node in nodes:
        plain[node] = sorted(set(plain[node]))
    return plain


def _tarjan_scc(nodes_subset: list[str], adjacency: dict[str, list[str]]) -> list[list[str]]:
    allowed = set(nodes_subset)
    filtered = {node: [nb for nb in adjacency.get(node, []) if nb in allowed] for node in nodes_subset}
    index_counter = itertools.count()
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(v: str) -> None:
        call_stack: list[tuple[str, int, list[str]]] = [(v, 0, filtered[v])]
        indices[v] = next(index_counter)
        lowlink[v] = indices[v]
        stack.append(v)
        on_stack.add(v)
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

    for node in sorted(nodes_subset):
        if node not in indices:
            strongconnect(node)
    components.sort(key=lambda comp: (-len(comp), comp))
    return components


def _single_source_shortest_paths(source: str, adjacency: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Fraction], dict[str, dict[str, Any] | None]]:
    distance: dict[str, Fraction] = {source: Fraction(0)}
    parent: dict[str, dict[str, Any] | None] = {}
    serial = itertools.count()
    heap: list[tuple[Fraction, int, str]] = [(Fraction(0), next(serial), source)]
    while heap:
        cost, _, node = heapq.heappop(heap)
        if cost != distance.get(node, Fraction(10**100)):
            continue
        for edge in adjacency.get(node, []):
            candidate = cost + Fraction(edge["cost"]["exact"])
            target = edge["target_state_id"]
            if candidate < distance.get(target, Fraction(10**100)):
                distance[target] = candidate
                parent[target] = edge
                heapq.heappush(heap, (candidate, next(serial), target))
    return distance, parent


def _reconstruct_path(source: str, target: str, parent: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cursor = target
    while cursor != source:
        edge = parent.get(cursor)
        if edge is None:
            return []
        result.append(edge)
        cursor = edge["source_state_id"]
    return list(reversed(result))


def _select_state_set_C(
    all_nodes: dict[str, State],
    requested_ids: list[str] | None,
    maximum: int,
) -> tuple[list[str], list[str], list[str]]:
    invalid: list[str] = []
    duplicates: list[str] = []
    if requested_ids:
        seen: set[str] = set()
        valid_unique: list[str] = []
        for item in requested_ids:
            if not isinstance(item, str):
                invalid.append(str(item))
                continue
            if item in seen:
                duplicates.append(item)
            else:
                seen.add(item)
                if item not in all_nodes:
                    invalid.append(item)
                else:
                    valid_unique.append(item)
        selected_base = sorted(valid_unique)
    else:
        selected_base = sorted(all_nodes)
    if len(selected_base) > maximum:
        selected_base = selected_base[:maximum]
    return selected_base, invalid, duplicates


def _verify_metric_exact(matrix: list[list[Fraction]], state_ids: list[str]) -> dict[str, Any]:
    n = len(matrix)
    nonnegative_failures: list[dict[str, Any]] = []
    identity_failures: list[dict[str, Any]] = []
    symmetry_failures: list[dict[str, Any]] = []
    separation_failures: list[dict[str, Any]] = []
    triangle_failures: list[dict[str, Any]] = []
    triples_tested = 0
    for i in range(n):
        for j in range(n):
            val = matrix[i][j]
            if val < 0:
                nonnegative_failures.append({"i": state_ids[i], "j": state_ids[j], "value": _frac_payload(val)})
        if matrix[i][i] != 0:
            identity_failures.append({"state": state_ids[i], "value": _frac_payload(matrix[i][i])})
        for j in range(n):
            if matrix[i][j] != matrix[j][i]:
                symmetry_failures.append({
                    "X": state_ids[i], "Y": state_ids[j],
                    "D_XY": _frac_payload(matrix[i][j]),
                    "D_YX": _frac_payload(matrix[j][i]),
                })
            if i != j and matrix[i][j] <= 0:
                separation_failures.append({"X": state_ids[i], "Y": state_ids[j], "value": _frac_payload(matrix[i][j])})
    for i in range(n):
        for j in range(n):
            for k in range(n):
                triples_tested += 1
                left = matrix[i][k]
                right = matrix[i][j] + matrix[j][k]
                if not (left <= right):
                    triangle_failures.append({
                        "X": state_ids[i], "Y": state_ids[j], "Z": state_ids[k],
                        "D_XZ": _frac_payload(left),
                        "D_XY_plus_YZ": _frac_payload(right),
                        "excess": _frac_payload(left - right),
                    })
                    if len(triangle_failures) >= 500:
                        break
            if len(triangle_failures) >= 500:
                break
        if len(triangle_failures) >= 500:
            break
    all_passed = (
        not nonnegative_failures
        and not identity_failures
        and not symmetry_failures
        and not separation_failures
        and not triangle_failures
    )
    return {
        "nonnegative": {"passed": not nonnegative_failures, "failures": nonnegative_failures},
        "identity": {"passed": not identity_failures, "failures": identity_failures},
        "symmetry": {"passed": not symmetry_failures, "failures": symmetry_failures},
        "separation": {"passed": not separation_failures, "failures": separation_failures},
        "triangle_inequality": {
            "passed": not triangle_failures,
            "tested_triples": triples_tested,
            "failures": triangle_failures,
        },
        "all_passed": all_passed,
        "arithmetic": "Exact Fractions; sin tolerancias flotantes.",
    }


def _ph_public_block(ph_result: dict[str, Any], metric_label: str) -> dict[str, Any]:
    ph = ph_result["persistent_homology"]
    intervals = ph["intervals"]
    betti_curve = ph["betti_curve"]
    critical_scales = ph["critical_scales"]
    betti_H0 = [float(point["beta_0"]) for point in betti_curve]
    betti_H1 = [float(point["beta_1"]) for point in betti_curve]
    features = []
    for dim_key in ("H0", "H1"):
        for feature in intervals.get(dim_key, []):
            features.append(feature)
    representatives_selected = []
    for feature_id, rep in ph.get("representatives", {}).items():
        representatives_selected.append({
            "feature_id": feature_id,
            **rep,
        })
    return {
        "status": "CALCULATED",
        "metric": metric_label,
        "critical_scales": critical_scales,
        "betti": {
            "H0": betti_H0,
            "H1": betti_H1,
        },
        "betti_curve": betti_curve,
        "features": features,
        "selected_representatives": representatives_selected,
        "summary": ph.get("summary", {}),
        "warnings": ph.get("warnings", []),
        "settings": {
            "complex": "Vietoris-Rips",
            "coefficients": f"F_{ph['settings']['coefficient_field']}",
            "dimensions": [0, 1],
            **{k: v for k, v in ph["settings"].items() if k != "coefficient_field"},
        },
        "algorithm": ph.get("algorithm", {}),
        "source": ph.get("source", {}),
        "selection": ph.get("selection", {}),
    }


def _count_features_by_dimension(ph_block: dict[str, Any], dimension: int) -> int:
    return sum(1 for feature in ph_block.get("features", []) if feature.get("dimension") == dimension)


def _interval_multiset(ph_block: dict[str, Any], dimension: int) -> list[tuple[str | None, str | None]]:
    """Canonical, order-independent multiset of persistence intervals.

    Returns a sorted list of ``(birth_exact, death_exact)`` pairs. ``death`` is
    ``None`` for the essential/infinite interval. ``feature_id`` is ignored, so
    two modules agree iff their exact interval content coincides.
    """
    intervals: list[tuple[str | None, str | None]] = []
    for feature in ph_block.get("features", []):
        if feature.get("dimension") != dimension:
            continue
        birth = (feature.get("birth") or {}).get("exact")
        death = (feature.get("death") or {}).get("exact")
        intervals.append((birth, death))
    intervals.sort(key=lambda pair: (pair[0] or "", pair[1] is None, pair[1] or ""))
    return intervals


def _finite_death_scales(ph_block: dict[str, Any], dimension: int) -> list[Fraction]:
    deaths: list[Fraction] = []
    for feature in ph_block.get("features", []):
        if feature.get("dimension") != dimension:
            continue
        death = (feature.get("death") or {}).get("exact")
        if death is not None:
            deaths.append(Fraction(death))
    return sorted(deaths)


def _beta0_at(deaths: list[Fraction], scale: Fraction) -> int:
    # One essential component plus every finite death strictly greater than scale.
    return 1 + sum(1 for d in deaths if d > scale)


def _first_divergence_scale(str_deaths: list[Fraction], op_deaths: list[Fraction]) -> Fraction | None:
    """Smallest scale where the cumulative H0 merge counts first differ."""
    for scale in sorted(set(str_deaths) | set(op_deaths)):
        c_str = sum(1 for d in str_deaths if d <= scale)
        c_op = sum(1 for d in op_deaths if d <= scale)
        if c_str != c_op:
            return scale
    return None




def _finalize_common_base(common_base):
    """Ensure every return path of compare_topologies exposes a consistent
    ai_topology_certification field marked as NON-NORMATIVE COMMENTARY.

    The AI narrative NEVER drives certification: validation_summary and
    topology_status are computed exclusively from deterministic fields. The
    AI block is kept only as explanatory commentary and is never read by the
    certification logic. NEVER raises.
    """
    if "ai_topology_certification" not in common_base:
        common_base["ai_topology_certification"] = {
            "role": "NON_NORMATIVE_COMMENTARY",
            "normative": False,
            "status": "SKIPPED_PIPELINE_ABORT",
            "failed_stage": common_base.get("failed_stage"),
            "blocking_reason": common_base.get("blocking_reason"),
        }
    else:
        common_base["ai_topology_certification"].setdefault("role", "NON_NORMATIVE_COMMENTARY")
        common_base["ai_topology_certification"].setdefault("normative", False)
    return common_base

def compare_topologies(payload: dict[str, Any]) -> dict[str, Any]:
    parameters = payload.get("parameters")
    profile = operational_weights(parameters)
    cost_profile_block = {name: rational_payload(value) for name, value in profile.items()}

    generated_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    engine_block = {
        "application": "chapter-5-operations",
        "port": 8002,
        "version": SOFTWARE_VERSION,
        "git_commit": GIT_COMMIT,
        "runtime": f"Python {platform.python_version()}",
    }

    explored_graph = payload.get("explored_graph")
    search_envelope_in = payload.get("search_envelope") or payload.get("envelope")
    topology_settings = payload.get("topology_settings") or payload.get("topology_parameters") or {}
    _PH_ALLOWED_SETTINGS = {"max_epsilon", "selection_rule", "scale_rule", "zero_distance_mode"}
    ph_settings = {key: topology_settings[key] for key in _PH_ALLOWED_SETTINGS if key in topology_settings}

    common_base: dict[str, Any] = {
        "report_type": REPORT_TYPE,
        "report_goal": REPORT_GOAL,
        "generated_at": generated_at,
        "engine": engine_block,
        "exact_arithmetic": "fractions.Fraction",
        "cost_profile": cost_profile_block,
        "search_envelope": search_envelope_in or {},
        "topology_parameters": {
            "complex": "Vietoris-Rips",
            "coefficients": "F_2",
            "dimensions": [0, 1],
            **topology_settings,
        },
    }

    if not isinstance(explored_graph, dict):
        common_base.update({
            "topology_status": "TOPOLOGY_NOT_COMPUTED",
            "failed_stage": "graph_materialization",
            "blocking_reason": "No se proporcionó explored_graph materializado.",
            "operational_graph": None,
            "state_set_C": {"cardinality": 0, "state_ids": [], "states": []},
            "strong_connectivity": None,
            "directed_Delta_R": None,
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        return _finalize_common_base(common_base)
    try:
        nodes, edges, graph_id = _graph(explored_graph, parameters)
    except OperationalError as exc:
        common_base.update({
            "topology_status": "TOPOLOGY_NOT_COMPUTED",
            "failed_stage": "graph_validation",
            "blocking_reason": str(exc),
            "operational_graph": None,
            "state_set_C": {"cardinality": 0, "state_ids": [], "states": []},
            "strong_connectivity": None,
            "directed_Delta_R": None,
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        return _finalize_common_base(common_base)
    weighted_adj = _weighted_adjacency(nodes, edges)
    plain_adj = _plain_adjacency(nodes, edges)

    # ============================================================
    # NUEVO · PASO 0: SCCs sobre TODO el G_R (no solo sobre C)
    # Política: G_R → SCC(G_R) → nontrivial largest → C ⊆ largest_scc
    # ============================================================
    all_node_ids = sorted(nodes.keys())
    sccs_over_all = _tarjan_scc(all_node_ids, plain_adj)
    nontrivial_sccs_all = [c for c in sccs_over_all if len(c) >= 2]
    scc_count_all = len(sccs_over_all)
    nontrivial_scc_count_all = len(nontrivial_sccs_all)
    largest_scc_all = sccs_over_all[0] if sccs_over_all else []
    largest_scc_cardinality_all = len(largest_scc_all)

    # Métricas auxiliares sobre largest_scc_all (si existe)
    largest_scc_edge_count_all = 0
    bidirectional_pair_count_all = 0
    dir_edge_set_no_loop: set[tuple[str, str]] = set()
    for e in edges:
        s, t = e["source_state_id"], e["target_state_id"]
        if s != t:
            dir_edge_set_no_loop.add((s, t))
    if nontrivial_sccs_all:
        _largest_set = set(largest_scc_all)
        largest_scc_edge_count_all = sum(
            1 for e in edges
            if e["source_state_id"] in _largest_set and e["target_state_id"] in _largest_set
        )
        checked: set[tuple[str, str]] = set()
        for a in largest_scc_all:
            for b in largest_scc_all:
                if a >= b:
                    continue
                p = (a, b)
                if p in checked:
                    continue
                checked.add(p)
                if (a, b) in dir_edge_set_no_loop and (b, a) in dir_edge_set_no_loop:
                    bidirectional_pair_count_all += 1
    graph_level_scc_block: dict[str, Any] = {
        "computed_over": "ENTIRE_G_R_nodes",
        "scc_count": scc_count_all,
        "nontrivial_scc_count": nontrivial_scc_count_all,
        "largest_scc_cardinality": largest_scc_cardinality_all,
        "largest_scc_edge_count": largest_scc_edge_count_all,
        "largest_scc_state_ids": list(largest_scc_all),
        "bidirectional_nonstationary_pair_count": bidirectional_pair_count_all,
        "scc_components": [
            {
                "component_id": f"scc-graph-{i+1}-size-{len(c)}",
                "cardinality": len(c),
                "state_ids": list(c),
            }
            for i, c in enumerate(sccs_over_all)
        ],
    }

    materialize_flag = bool(
        (explored_graph.get("edge_materialization_complete") if isinstance(explored_graph, dict) else False)
        or (explored_graph.get("materialize_full_graph") if isinstance(explored_graph, dict) else False)
        or (search_envelope_in.get("materialize_full_graph") if isinstance(search_envelope_in, dict) else False)
        or len(edges) > 0
    )

    operational_graph_block: dict[str, Any] = {
        "graph_id": graph_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "materialized_full_graph": materialize_flag,
        "graph_scc_statistics": graph_level_scc_block,
        "nodes": [
            {
                "state_id": identifier,
                "state": state_payload(nodes[identifier]),
            }
            for identifier in sorted(nodes)
        ],
        "edges": [
            {
                "edge_id": edge["edge_id"],
                "source_state_id": edge["source_state_id"],
                "target_state_id": edge["target_state_id"],
                "action": edge["action"],
                "cost": edge["cost"],
                "canonically_inert": edge["canonically_inert"],
                "normalization_effective": edge["normalization_effective"],
                "transition_ref": edge["transition_ref"],
            }
            for edge in edges
        ],
    }

    if len(nodes) < 2 or len(edges) < 1:
        common_base.update({
            "topology_status": "INSUFFICIENT_OPERATIONAL_GRAPH",
            "failed_stage": "graph_materialization_check",
            "blocking_reason": (
                "G_R debe tener más de un nodo y al menos una arista para el experimento "
                f"topológico. Se obtuvo node_count={len(nodes)}, edge_count={len(edges)}."
            ),
            "operational_graph": operational_graph_block,
            "state_set_C": {"cardinality": 0, "state_ids": [], "states": []},
            "strong_connectivity": None,
            "directed_Delta_R": None,
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        return _finalize_common_base(common_base)
    # ============================================================
    # NUEVO · EARLY RETURN: si largest_scc_cardinality < 2
    # Bloquea ANTES de construir C, Delta_R, D_op o PH
    # ============================================================
    if largest_scc_cardinality_all < 2:
        common_base.update({
            "topology_status": "INSUFFICIENT_NONTRIVIAL_SCC",
            "failed_stage": "operational_scc_preselection",
            "blocking_reason": (
                "No existe ninguna componente fuertemente conexa no trivial en G_R. "
                "La SCC más grande tiene cardinalidad "
                f"{largest_scc_cardinality_all}. Se requiere al menos |SCC| ≥ 2 para "
                "construir C_R*. delta_R es distancia de caminos mínimos DENTRO de G_R finito; "
                "no se afirma representar el ínfimo global δ_T."
            ),
            "operational_graph": operational_graph_block,
            "state_set_C": {"cardinality": 0, "state_ids": [], "states": []},
            "strong_connectivity": None,
            "directed_Delta_R": None,
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        return _finalize_common_base(common_base)
    maximum = payload.get("max_states", 24)
    if type(maximum) is not int or not 2 <= maximum <= TOPOLOGY_STATE_LIMIT:
        raise OperationalError(f"max_states debe estar entre 2 y {TOPOLOGY_STATE_LIMIT}")

    requested_ids = payload.get("state_ids")
    invalid_ids: list[str] = []
    duplicate_ids: list[str] = []

    # ============================================================
    # NUEVA POLÍTICA DE SELECCIÓN C:
    #   Si usuario NO envía state_ids manuales → candidates_base = largest_scc (ordenado)
    #   Si usuario SÍ envía state_ids manuales:
    #     - Si todos (o varios) pertenecen a UNA MISMA SCC nontrivial (puede ser que
    #       no sea la largest) → se usa ESA SCC nontrivial (advertencia informativa)
    #     - Sino → intersectar con largest_scc nontrivial.
    # ============================================================
    selected_scc_for_C = list(largest_scc_all)
    selected_scc_id_for_log = f"scc-largest-size-{len(selected_scc_for_C)}"
    user_scc_override_warning: dict[str, Any] | None = None

    if requested_ids:
        seen_req: set[str] = set()
        valid_unique_req: list[str] = []
        for item in requested_ids:
            if not isinstance(item, str):
                invalid_ids.append(str(item))
                continue
            if item in seen_req:
                duplicate_ids.append(item)
            else:
                seen_req.add(item)
                if item not in nodes:
                    invalid_ids.append(item)
                else:
                    valid_unique_req.append(item)
        # Determinar la SCC de cada id válido pedido por usuario
        req_scc_membership: dict[int, list[str]] = {}
        for sid in valid_unique_req:
            for idx_scc, comp in enumerate(nontrivial_sccs_all):
                if sid in comp:
                    req_scc_membership.setdefault(idx_scc, []).append(sid)
                    break
        if req_scc_membership:
            # Escoger la SCC nontrivial con más state_ids válidos pedidos por usuario
            best_idx = max(req_scc_membership, key=lambda k: len(req_scc_membership[k]))
            if len(req_scc_membership[best_idx]) >= 2:
                comp = nontrivial_sccs_all[best_idx]
                if set(comp) != set(selected_scc_for_C):
                    user_scc_override_warning = {
                        "warning": "USER_STATE_IDS_MAP_TO_NON_LARGEST_NONTRIVIAL_SCC",
                        "requested_ids_in_scc": req_scc_membership[best_idx],
                        "scc_size": len(comp),
                        "largest_scc_size": len(selected_scc_for_C),
                        "note": "Se usa la SCC solicitada por el usuario (nontrivial pero no la mayor).",
                    }
                selected_scc_for_C = list(comp)
                selected_scc_id_for_log = f"scc-user-picked-size-{len(comp)}"
            candidates_base = sorted(set(valid_unique_req) & set(selected_scc_for_C))
            if len(candidates_base) < 2:
                # No hay suficientes ids de usuario en la SCC escogida; añadir el resto desde la SCC
                remaining = [s for s in sorted(selected_scc_for_C) if s not in candidates_base]
                candidates_base = candidates_base + remaining
        else:
            # Ningún id válido está en ninguna SCC nontrivial → fallback a largest_scc
            candidates_base = sorted(set(valid_unique_req) & set(selected_scc_for_C))
            if len(candidates_base) < 2:
                candidates_base = sorted(selected_scc_for_C)
    else:
        candidates_base = sorted(selected_scc_for_C)

    # Limitar a max_states
    if len(candidates_base) > maximum:
        candidates_base = candidates_base[:maximum]
    candidates = candidates_base

    # Garantía: si candidates_base terminó teniendo <2 (caso extremo raro), ampliamos
    if len(candidates) < 2:
        for c in nontrivial_sccs_all:
            if len(c) >= 2:
                candidates = sorted(c)[:maximum]
                break

    state_set_C: dict[str, Any] = {
        "cardinality": len(candidates),
        "state_ids": list(candidates),
        "states": [
            {"state_id": sid, "state": state_payload(nodes[sid])}
            for sid in candidates
        ],
        "selection_policy": "C_WITHIN_LARGEST_NONTRIVIAL_SCC_OF_G_R",
        "C_selection_scope": "SINGLE_SCC_OF_ENTIRE_G_R",
        "selected_scc_id": selected_scc_id_for_log,
    }
    if user_scc_override_warning:
        state_set_C["user_scc_override"] = user_scc_override_warning

    if len(candidates) < 2:
        common_base.update({
            "topology_status": "INSUFFICIENT_NONTRIVIAL_SCC",
            "failed_stage": "C_selection_within_SCC",
            "blocking_reason": (
                "Después de restringir C a la SCC nontrivial más grande, el conjunto "
                f"resultante tiene |C|={len(candidates)} < 2. Se requiere al menos 2."
            ),
            "operational_graph": operational_graph_block,
            "state_set_C": state_set_C,
            "strong_connectivity": None,
            "directed_Delta_R": None,
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        if invalid_ids:
            common_base["invalid_state_ids_provided"] = invalid_ids
        if duplicate_ids:
            common_base["duplicate_state_ids_provided"] = duplicate_ids
        return _finalize_common_base(common_base)
    # NOTA: eliminamos la exigencia anterior de |C| >= 4. Ahora |C| >= 2 basta teóricamente.
    # ============================================================
    # CORRECCIÓN SEMÁNTICA · C_R_star = C
    # ============================================================
    # C fue seleccionado DENTRO de UNA MISMA SCC del G_R completo. Por tanto todos
    # sus elementos son mutuamente alcanzables en G_R completo, y delta_R(X,Y) =
    # dist_{G_R}(X,Y) se define sobre TODO G_R (los caminos pueden atravesar estados
    # intermedios fuera de C). NO se reduce C por la SCC del subgrafo inducido G_R[C].
    C_R_star_raw = list(candidates)  # == C, mismo orden

    distances_all: dict[str, dict[str, Fraction]] = {}
    parents_all: dict[str, dict[str, dict[str, Any] | None]] = {}
    for source in C_R_star_raw:
        distances_all[source], parents_all[source] = _single_source_shortest_paths(source, weighted_adj)

    nonfinite_pairs_list: list[tuple[str, str]] = []
    for i, x in enumerate(C_R_star_raw):
        for j, y in enumerate(C_R_star_raw):
            if distances_all.get(x, {}).get(y) is None:
                nonfinite_pairs_list.append((x, y))

    # Diagnóstico OPCIONAL (nunca excluyente): SCC del subgrafo inducido G_R[C].
    induced_sccs = _tarjan_scc(C_R_star_raw, plain_adj)
    all_pairs_reachable_in_G_R = bool(C_R_star_raw) and not nonfinite_pairs_list

    strong_connectivity_block: dict[str, Any] = {
        "C_selection_scope": "SINGLE_SCC_OF_ENTIRE_G_R",
        "distance_path_scope": "ENTIRE_G_R",
        "C_R_star_reachability_scope": "ENTIRE_G_R",
        "induced_subgraph_connectivity_required": False,
        "C_R_star": {
            "cardinality": len(C_R_star_raw),
            "state_ids": list(C_R_star_raw),
            "exclusions": [],
        },
        "excluded_states": [],
        "all_pairs_mutually_reachable_in_G_R": all_pairs_reachable_in_G_R,
        "induced_subgraph_scc_diagnostic": {
            "computed_for_diagnosis_only": True,
            "does_not_drive_C_R_star_selection": True,
            "scc_count": len(induced_sccs),
            "largest_induced_scc_cardinality": len(induced_sccs[0]) if induced_sccs else 0,
        },
    }

    if len(C_R_star_raw) < 2:
        common_base.update({
            "topology_status": "INSUFFICIENT_STRONGLY_CONNECTED_SUBSET",
            "failed_stage": "C_R_star_selection",
            "blocking_reason": (
                "C_R_star debe ser un subconjunto no trivial con al menos 2 estados mutuamente "
                f"alcanzables. Se obtuvo |C_R_star|={len(C_R_star_raw)}. "
                f"Pares no finitos detectados: {len(nonfinite_pairs_list)}."
            ),
            "operational_graph": operational_graph_block,
            "state_set_C": state_set_C,
            "strong_connectivity": strong_connectivity_block,
            "directed_Delta_R": None,
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        if invalid_ids:
            common_base["invalid_state_ids_provided"] = invalid_ids
        if duplicate_ids:
            common_base["duplicate_state_ids_provided"] = duplicate_ids
        return _finalize_common_base(common_base)
    C_R_star_ids = list(C_R_star_raw)
    n = len(C_R_star_ids)
    delta_R_raw: list[list[Fraction | None]] = [[None for _ in range(n)] for _ in range(n)]
    all_finite = True
    for i, x in enumerate(C_R_star_ids):
        for j, y in enumerate(C_R_star_ids):
            val = distances_all.get(x, {}).get(y)
            delta_R_raw[i][j] = val
            if val is None:
                all_finite = False

    if not all_finite:
        common_base.update({
            "topology_status": "NONFINITE_OPERATIONAL_DISTANCES",
            "failed_stage": "Delta_R_shortest_paths_internal_to_G_R",
            "blocking_reason": (
                "Hay pares (X,Y) en C_R_star sin camino finito interno a G_R. "
                "Delta_R requiere todos los pares finitos dentro del grafo materializado."
            ),
            "operational_graph": operational_graph_block,
            "state_set_C": state_set_C,
            "strong_connectivity": strong_connectivity_block,
            "directed_Delta_R": {
                "state_ids": list(C_R_star_ids),
                "matrix": [
                    [None if delta_R_raw[i][j] is None else _frac_payload(delta_R_raw[i][j]) for j in range(n)]
                    for i in range(n)
                ],
                "nonfinite_pair_locations": [
                    {"i": C_R_star_ids[x], "j": C_R_star_ids[y]}
                    for x, y in nonfinite_pairs_list
                ],
            },
            "asymmetry_A_R": None,
            "operational_D_op": None,
            "metric_checks": None,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        if invalid_ids:
            common_base["invalid_state_ids_provided"] = invalid_ids
        if duplicate_ids:
            common_base["duplicate_state_ids_provided"] = duplicate_ids
        return _finalize_common_base(common_base)
    delta_R_fractions: list[list[Fraction]] = [
        [Fraction(0) for _ in range(n)] for _ in range(n)
    ]
    directed_delta_payload: list[list[dict[str, Any]]] = []
    diagonal_zero_ok = True
    for i in range(n):
        row_payload = []
        for j in range(n):
            value = delta_R_raw[i][j]
            assert value is not None
            delta_R_fractions[i][j] = value
            row_payload.append(_frac_payload(value))
        directed_delta_payload.append(row_payload)
    for i in range(n):
        if delta_R_fractions[i][i] != 0:
            diagonal_zero_ok = False
            break

    directed_Delta_R_block: dict[str, Any] = {
        "state_ids": list(C_R_star_ids),
        "matrix": directed_delta_payload,
        "diagonal_zero_exact": diagonal_zero_ok,
        "all_entries_finite_internal_to_G_R": True,
        "construction_rule": "shortest_path_cost_G_R(X_i,X_j) sobre el mismo G_R.",
    }

    asymmetry_fractions: list[list[Fraction]] = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    nonzero_pairs: list[dict[str, Any]] = []
    max_asy = Fraction(0)
    total_asy = Fraction(0)
    pair_count_asy = 0
    for i in range(n):
        for j in range(n):
            diff = abs(delta_R_fractions[i][j] - delta_R_fractions[j][i])
            asymmetry_fractions[i][j] = diff
            if diff > max_asy:
                max_asy = diff
            if i != j:
                total_asy += diff
                pair_count_asy += 1
            if diff != 0 and i < j:
                nonzero_pairs.append({
                    "X": C_R_star_ids[i],
                    "Y": C_R_star_ids[j],
                    "delta_forward": _frac_payload(delta_R_fractions[i][j]),
                    "delta_backward": _frac_payload(delta_R_fractions[j][i]),
                    "asymmetry_abs": _frac_payload(diff),
                })
    mean_asy = total_asy / pair_count_asy if pair_count_asy > 0 else Fraction(0)
    asymmetry_matrix_payload = [
        [_frac_payload(asymmetry_fractions[i][j]) for j in range(n)]
        for i in range(n)
    ]
    asymmetry_A_R_block: dict[str, Any] = {
        "state_ids": list(C_R_star_ids),
        "matrix": asymmetry_matrix_payload,
        "max_asymmetry": _frac_payload(max_asy),
        "mean_asymmetry": _frac_payload(mean_asy),
        "nonzero_pairs": nonzero_pairs,
        "definition": "A_R(X,Y) = |delta_R(X,Y) - delta_R(Y,X)|",
    }

    D_op_fractions: list[list[Fraction]] = [
        [(delta_R_fractions[i][j] + delta_R_fractions[j][i]) / 2 for j in range(n)]
        for i in range(n)
    ]
    D_op_payload: list[list[dict[str, Any]]] = [
        [_frac_payload(D_op_fractions[i][j]) for j in range(n)]
        for i in range(n)
    ]
    operational_D_op_block: dict[str, Any] = {
        "definition": "(delta_R(X,Y)+delta_R(Y,X))/2, especialización experimental derivada de G_R. NO es delta_T.",
        "state_ids": list(C_R_star_ids),
        "matrix": D_op_payload,
    }

    metric_checks_block = _verify_metric_exact(D_op_fractions, C_R_star_ids)

    if not metric_checks_block["all_passed"]:
        common_base.update({
            "topology_status": "OPERATIONAL_TOPOLOGY_BLOCKED_NON_METRIC",
            "failed_stage": "metric_checks_D_op",
            "blocking_reason": (
                "D_op no satisface exactamente los axiomas de métrica. "
                "Se cancela la ejecución de PH_operational_R."
            ),
            "operational_graph": operational_graph_block,
            "state_set_C": state_set_C,
            "strong_connectivity": strong_connectivity_block,
            "directed_Delta_R": directed_Delta_R_block,
            "asymmetry_A_R": asymmetry_A_R_block,
            "operational_D_op": operational_D_op_block,
            "metric_checks": metric_checks_block,
            "structural_D_str": None,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        if invalid_ids:
            common_base["invalid_state_ids_provided"] = invalid_ids
        if duplicate_ids:
            common_base["duplicate_state_ids_provided"] = duplicate_ids
        return _finalize_common_base(common_base)
    D_str_fractions: list[list[Fraction]] = [[Fraction(0) for _ in range(n)] for _ in range(n)]
    structural_certificates_by_ij: dict[tuple[int, int], dict[str, Any]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            certificate = compare_states(nodes[C_R_star_ids[i]], nodes[C_R_star_ids[j]], parameters)
            value = Fraction(certificate["distance"]["exact"])
            D_str_fractions[i][j] = D_str_fractions[j][i] = value
            structural_certificates_by_ij[(i, j)] = certificate
    D_str_payload: list[list[dict[str, Any]]] = [
        [_frac_payload(D_str_fractions[i][j]) for j in range(n)]
        for i in range(n)
    ]
    structural_D_str_block: dict[str, Any] = {
        "metric": "D_gamma",
        "state_ids": list(C_R_star_ids),
        "matrix": D_str_payload,
    }

    matrix_exact_strings_D_str = [[D_str_payload[i][j]["exact"] for j in range(n)] for i in range(n)]
    matrix_exact_strings_D_op = [[D_op_payload[i][j]["exact"] for j in range(n)] for i in range(n)]

    try:
        structural_ph_raw = compute_persistent_homology(
            list(C_R_star_ids), matrix_exact_strings_D_str, parameters=parameters, settings=ph_settings,
        )
    except PersistentHomologyError as exc:
        common_base.update({
            "topology_status": "STRUCTURAL_PH_FAILED",
            "failed_stage": "PH_structural_computation_over_D_str",
            "blocking_reason": str(exc),
            "operational_graph": operational_graph_block,
            "state_set_C": state_set_C,
            "strong_connectivity": strong_connectivity_block,
            "directed_Delta_R": directed_Delta_R_block,
            "asymmetry_A_R": asymmetry_A_R_block,
            "operational_D_op": operational_D_op_block,
            "metric_checks": metric_checks_block,
            "structural_D_str": structural_D_str_block,
            "PH_structural": None,
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        if invalid_ids:
            common_base["invalid_state_ids_provided"] = invalid_ids
        if duplicate_ids:
            common_base["duplicate_state_ids_provided"] = duplicate_ids
        return _finalize_common_base(common_base)
    try:
        operational_ph_raw = compute_persistent_homology(
            list(C_R_star_ids), matrix_exact_strings_D_op, parameters=parameters, settings=ph_settings,
        )
    except PersistentHomologyError as exc:
        common_base.update({
            "topology_status": "OPERATIONAL_PH_FAILED",
            "failed_stage": "PH_operational_R_computation_over_D_op",
            "blocking_reason": str(exc),
            "operational_graph": operational_graph_block,
            "state_set_C": state_set_C,
            "strong_connectivity": strong_connectivity_block,
            "directed_Delta_R": directed_Delta_R_block,
            "asymmetry_A_R": asymmetry_A_R_block,
            "operational_D_op": operational_D_op_block,
            "metric_checks": metric_checks_block,
            "structural_D_str": structural_D_str_block,
            "PH_structural": _ph_public_block(structural_ph_raw, "D_gamma"),
            "PH_operational_R": None,
            "comparison": None,
            "selected_representatives": None,
            "traceability_records": [],
            "validation_summary": None,
        })
        if invalid_ids:
            common_base["invalid_state_ids_provided"] = invalid_ids
        if duplicate_ids:
            common_base["duplicate_state_ids_provided"] = duplicate_ids
        return _finalize_common_base(common_base)
    PH_structural_block = _ph_public_block(structural_ph_raw, "D_gamma")
    PH_operational_block = _ph_public_block(operational_ph_raw, "D_op")

    structural_H0_intervals = _interval_multiset(PH_structural_block, 0)
    operational_H0_intervals = _interval_multiset(PH_operational_block, 0)
    structural_H0_count = len(structural_H0_intervals)
    operational_H0_count = len(operational_H0_intervals)
    structural_H1_count = _count_features_by_dimension(PH_structural_block, 1)
    operational_H1_count = _count_features_by_dimension(PH_operational_block, 1)

    # H0 se compara por el CONTENIDO de los intervalos persistentes (multiset exacto),
    # no por el número de features. H1 se mantiene por recuento (scope del cambio).
    H0_agrees = structural_H0_intervals == operational_H0_intervals
    H1_agrees = structural_H1_count == operational_H1_count
    topology_agrees = H0_agrees and H1_agrees
    persistent_homology_signatures_agree = topology_agrees
    operational_topology_distinguishes = not topology_agrees

    differences_H0: list[dict[str, Any]] = []
    differences_H1: list[dict[str, Any]] = []
    if not H0_agrees:
        str_deaths = _finite_death_scales(PH_structural_block, 0)
        op_deaths = _finite_death_scales(PH_operational_block, 0)
        first_scale = _first_divergence_scale(str_deaths, op_deaths)
        differences_H0.append({
            "type": "H0_persistence_interval_mismatch",
            "structural_feature_count": structural_H0_count,
            "operational_feature_count": operational_H0_count,
            "structural_death_scales": [_exact_str(d) for d in str_deaths],
            "operational_death_scales": [_exact_str(d) for d in op_deaths],
            "first_divergence_scale": _exact_str(first_scale) if first_scale is not None else None,
            "structural_beta0_at_first_divergence": _beta0_at(str_deaths, first_scale) if first_scale is not None else None,
            "operational_beta0_at_first_divergence": _beta0_at(op_deaths, first_scale) if first_scale is not None else None,
        })
    if structural_H1_count != operational_H1_count:
        differences_H1.append({
            "type": "H1_feature_count_mismatch",
            "structural_feature_count": structural_H1_count,
            "operational_feature_count": operational_H1_count,
        })

    if operational_topology_distinguishes:
        statement = (
            "Las filtraciones de Vietoris-Rips inducidas respectivamente por D_gamma y D_R_op "
            "presentan firmas de homología persistente distintas sobre el mismo conjunto C_R_star."
        )
    else:
        statement = (
            "Las filtraciones de Vietoris-Rips inducidas respectivamente por D_gamma y D_R_op "
            "presentan la misma firma de homología persistente sobre el mismo conjunto C_R_star."
        )

    comparison_block: dict[str, Any] = {
        "same_state_set": structural_D_str_block["state_ids"] == operational_D_op_block["state_ids"],
        "persistent_homology_signatures_agree": persistent_homology_signatures_agree,
        "H0": {
            "agrees": H0_agrees,
            "structural_feature_count": structural_H0_count,
            "operational_feature_count": operational_H0_count,
            "differences": differences_H0,
        },
        "H1": {
            "agrees": H1_agrees,
            "structural_feature_count": structural_H1_count,
            "operational_feature_count": operational_H1_count,
            "differences": differences_H1,
        },
        "topology_agrees": topology_agrees,
        "operational_topology_distinguishes": operational_topology_distinguishes,
        "statement": statement,
        "note_1": "Todas las distancias operacionales son caminos mínimos INTERNOS a G_R.",
        "note_2": "PH_operational_R es PH_R^op: depende de G_R y no representa delta_T global.",
    }

    selected_representatives_block: dict[str, Any] = {
        "structural": list(PH_structural_block.get("selected_representatives", [])),
        "operational": list(PH_operational_block.get("selected_representatives", [])),
    }

    traceability_records: list[dict[str, Any]] = []
    difference_counter = itertools.count(1)
    for i in range(n):
        for j in range(i + 1, n):
            X = C_R_star_ids[i]
            Y = C_R_star_ids[j]
            struct_cert = structural_certificates_by_ij[(i, j)]
            matches = struct_cert.get("matches", [])
            substitutions = [m for m in matches if m.get("status") == "substituted"]
            insertions = struct_cert.get("insertions", [])
            deletions = struct_cert.get("deletions", [])
            components = struct_cert.get("components", {})

            fwd_path = _reconstruct_path(X, Y, parents_all.get(X, {}))
            bwd_path = _reconstruct_path(Y, X, parents_all.get(Y, {}))
            fwd_cost = delta_R_fractions[i][j]
            bwd_cost = delta_R_fractions[j][i]
            fwd_refs = [edge["transition_ref"] for edge in fwd_path]
            bwd_refs = [edge["transition_ref"] for edge in bwd_path]
            asy_val = asymmetry_fractions[i][j]
            # Secuencia de estados del camino en G_R COMPLETO. Los intermedios pueden
            # NO pertenecer a C_R_star ni a C (es válido: delta_R se define sobre G_R).
            fwd_state_seq = [X] + [edge["target_state_id"] for edge in fwd_path]
            bwd_state_seq = [Y] + [edge["target_state_id"] for edge in bwd_path]
            fwd_intermediate = fwd_state_seq[1:-1]
            bwd_intermediate = bwd_state_seq[1:-1]

            structural_pair_block: dict[str, Any] = {
                "X": X,
                "Y": Y,
                "D_gamma": _frac_payload(D_str_fractions[i][j]),
                "structural_certificate": {
                    "optimal_correspondence": matches,
                    "substitutions": substitutions,
                    "insertions": insertions,
                    "deletions": deletions,
                    "cost_components": components,
                },
            }
            operational_pair_block: dict[str, Any] = {
                "X": X,
                "Y": Y,
                "delta_R_XY": _frac_payload(fwd_cost),
                "delta_R_YX": _frac_payload(bwd_cost),
                "shortest_path_forward": {
                    "source_state_id": X,
                    "target_state_id": Y,
                    "distance": _frac_payload(fwd_cost),
                    "cost": _frac_payload(fwd_cost),
                    "step_count": len(fwd_path),
                    "transition_refs": fwd_refs,
                    "intermediate_state_ids": fwd_intermediate,
                    "steps": [
                        {
                            "transition_ref": edge["transition_ref"],
                            "source_state_id": edge["source_state_id"],
                            "target_state_id": edge["target_state_id"],
                            "action": edge["action"],
                            "cost": edge["cost"],
                        }
                        for edge in fwd_path
                    ],
                },
                "shortest_path_backward": {
                    "source_state_id": Y,
                    "target_state_id": X,
                    "distance": _frac_payload(bwd_cost),
                    "cost": _frac_payload(bwd_cost),
                    "step_count": len(bwd_path),
                    "transition_refs": bwd_refs,
                    "intermediate_state_ids": bwd_intermediate,
                    "steps": [
                        {
                            "transition_ref": edge["transition_ref"],
                            "source_state_id": edge["source_state_id"],
                            "target_state_id": edge["target_state_id"],
                            "action": edge["action"],
                            "cost": edge["cost"],
                        }
                        for edge in bwd_path
                    ],
                },
                "asymmetry": _frac_payload(asy_val),
            }

            rel_types: list[str] = []
            machine_parts: list[str] = []
            if D_str_fractions[i][j] < D_op_fractions[i][j]:
                rel_types.append("structural_closer_than_operational")
                machine_parts.append(f"{X} e {Y} se conectan a menor escala bajo D_gamma que bajo D_op.")
            elif D_op_fractions[i][j] < D_str_fractions[i][j]:
                rel_types.append("operational_closer_than_structural")
                machine_parts.append(f"{X} e {Y} se conectan a menor escala bajo D_op que bajo D_gamma.")
            else:
                rel_types.append("distances_equal_on_this_pair")
                machine_parts.append(f"{X} e {Y} tienen la misma escala de conexión bajo D_gamma y D_op.")

            difference_id = f"diff-{next(difference_counter):04d}"
            traceability_records.append({
                "difference_id": difference_id,
                "dimension": 0,
                "pairwise": True,
                "difference_types": rel_types,
                "involved_state_ids": [X, Y],
                "structural_pair": structural_pair_block,
                "operational_pair": operational_pair_block,
                "structural_relation_refs": [f"structural:{difference_id}"],
                "operational_relation_refs": [f"operational:{difference_id}"],
                "machine_statement": " ".join(machine_parts),
                "asymmetry": _frac_payload(asy_val),
            })

    structural_calculated = True
    operational_calculated = True
    traceability_record_count = len(traceability_records)
    traceability_complete = traceability_record_count == (n * (n - 1) // 2)
    if not traceability_complete:
        common_base.setdefault("topology_status_traceability", "TRACEABILITY_INCOMPLETE")
        topology_status = "TRACEABILITY_INCOMPLETE"
    else:
        topology_status = "TOPOLOGY_CERTIFIED"

    state_id_order_consistent = (
        directed_Delta_R_block["state_ids"] == operational_D_op_block["state_ids"]
        and directed_Delta_R_block["state_ids"] == structural_D_str_block["state_ids"]
        and directed_Delta_R_block["state_ids"] == strong_connectivity_block["C_R_star"]["state_ids"]
    )

    certification_passed = (
        len(nodes) >= 2
        and len(edges) >= 1
        and state_set_C["cardinality"] >= 2
        and strong_connectivity_block["C_R_star"]["cardinality"] >= 2
        and all_finite
        and directed_Delta_R_block is not None
        and asymmetry_A_R_block is not None
        and operational_D_op_block is not None
        and metric_checks_block["all_passed"]
        and state_id_order_consistent
        and structural_calculated
        and operational_calculated
        and comparison_block is not None
        and traceability_complete
    )

    validation_summary_block: dict[str, Any] = {
        "topology_status": topology_status,
        "operational_graph_id": graph_id,
        "graph_node_count": len(nodes),
        "graph_edge_count": len(edges),
        "C_cardinality": state_set_C["cardinality"],
        "C_R_star_cardinality": strong_connectivity_block["C_R_star"]["cardinality"],
        "C_R_star_exclusions": strong_connectivity_block["C_R_star"].get("exclusions", []),
        "all_operational_pairs_finite": all_finite,
        "metric_D_op": bool(metric_checks_block["all_passed"]),
        "persistent_homology": {
            "structural_calculated": structural_calculated,
            "operational_calculated": operational_calculated,
            "H0_agrees": H0_agrees,
            "H1_agrees": H1_agrees,
        },
        "operational_topology_distinguishes": operational_topology_distinguishes,
        "persistent_homology_signatures_agree": persistent_homology_signatures_agree,
        "traceability_record_count": traceability_record_count,
        "state_id_order_consistent": state_id_order_consistent,
        "same_state_set_structural_operational": state_id_order_consistent,
        "traceability_complete": traceability_complete,
        "certification_passed": bool(certification_passed),
        "epistemic_statement": (
            "PH_R^op depende del subgrafo operacional finito G_R y no constituye una estimación "
            "certificada de la topología asociada al ínfimo global delta_T."
        ),
    }

    common_base.update({
        "topology_status": topology_status,
        "operational_graph": operational_graph_block,
        "state_set_C": state_set_C,
        "strong_connectivity": strong_connectivity_block,
        "directed_Delta_R": directed_Delta_R_block,
        "asymmetry_A_R": asymmetry_A_R_block,
        "operational_D_op": operational_D_op_block,
        "metric_checks": metric_checks_block,
        "structural_D_str": structural_D_str_block,
        "PH_structural": PH_structural_block,
        "PH_operational_R": PH_operational_block,
        "comparison": comparison_block,
        "selected_representatives": selected_representatives_block,
        "traceability_records": traceability_records,
        "validation_summary": validation_summary_block,
    })
    if invalid_ids:
        common_base["invalid_state_ids_provided"] = invalid_ids
    if duplicate_ids:
        common_base["duplicate_state_ids_provided"] = duplicate_ids

    # AI certification narrative (non-blocking; never raises)
    try:
        _phs = PH_structural_block if isinstance(PH_structural_block, dict) else {}
        _pho = PH_operational_block if isinstance(PH_operational_block, dict) else {}
        def _ph_betti_ok(ph: dict) -> bool:
            cv = ph.get("betti_curve") or ph.get("betti_curves")
            if isinstance(cv, list):
                return len(cv) > 0
            if isinstance(cv, dict):
                return any(len(v) > 0 for v in cv.values() if isinstance(v, list))
            bb = ph.get("betti") or ph.get("barcodes") or ph.get("persistence_pairs")
            if isinstance(bb, list):
                return len(bb) > 0
            if isinstance(bb, dict):
                return any(len(v) > 0 for v in bb.values() if isinstance(v, list))
            return ph.get("status") in {"CALCULATED", "VALID", "OK"}

        og = operational_graph_block or {}
        gs = (og.get("graph_scc_statistics") or {}) if isinstance(og, dict) else {}
        sc = strong_connectivity_block or {}
        cr = sc.get("C_R_star") or sc.get("C") or {}
        axioms = {
            k: bool((metric_checks_block or {}).get(k, {}).get("passed", False))
            for k in ["nonnegative", "identity", "symmetry", "separation", "triangle_inequality"]
        }

        _request_payload = payload if isinstance(payload, dict) else {}
        ai_enabled = ai_summaries.ai_enabled_from_request(_request_payload)
        deterministic_inputs = {
            "topology_status": str(topology_status),
            "c_r_star_cardinality": int(cr.get("cardinality") or 0),
            "largest_scc_cardinality": int(gs.get("largest_scc_cardinality") or 0),
            "metric_all_passed": bool((metric_checks_block or {}).get("all_passed", False)),
            "per_axiom": axioms,
            "ph_structural_has_betti": _ph_betti_ok(_phs),
            "ph_operational_has_betti": _ph_betti_ok(_pho),
            "certification_passed": bool(validation_summary_block.get("certification_passed", False)),
            "operational_topology_distinguishes": bool(
                validation_summary_block.get("operational_topology_distinguishes", False)
            ),
            "persistent_homology_signatures_agree": bool(
                validation_summary_block.get("persistent_homology_signatures_agree", False)
            ),
        }
        ai_result = ai_summaries.summarize_topology_certification(
            ai_enabled,
            topology_status=deterministic_inputs["topology_status"],
            blocking_reason=common_base.get("blocking_reason"),
            c_r_star_cardinality=deterministic_inputs["c_r_star_cardinality"],
            largest_scc_cardinality=deterministic_inputs["largest_scc_cardinality"],
            metric_all_passed=deterministic_inputs["metric_all_passed"],
            per_axiom=deterministic_inputs["per_axiom"],
            ph_structural_has_betti=deterministic_inputs["ph_structural_has_betti"],
            ph_operational_has_betti=deterministic_inputs["ph_operational_has_betti"],
            certification_passed=deterministic_inputs["certification_passed"],
            operational_topology_distinguishes=deterministic_inputs["operational_topology_distinguishes"],
        )
        common_base["ai_topology_certification"] = {
            "role": "NON_NORMATIVE_COMMENTARY",
            "normative": False,
            "deterministic_inputs": deterministic_inputs,
            **ai_result,
        }
    except Exception as _e:  # noqa: BLE001 — blanket safe, never break topology
        common_base["ai_topology_certification"] = {
            "role": "NON_NORMATIVE_COMMENTARY",
            "normative": False,
            "status": "SKIPPED_API_ERROR",
            "reason": f"Unexpected wrapper: {type(_e).__name__}: {_e}",
        }

    return _finalize_common_base(common_base)
