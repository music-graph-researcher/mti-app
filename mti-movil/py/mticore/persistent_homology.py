"""Homología persistente H0/H1 exacta para espacios finitos MTI.

La filtración de Vietoris--Rips se ordena mediante rangos enteros de las
distancias racionales. La reducción de bordes se realiza sobre F_2 usando
enteros Python como bitsets, sin decidir empates mediante coma flotante.
"""

from __future__ import annotations

from bisect import bisect_right
from fractions import Fraction
from itertools import combinations
from statistics import median
from typing import Any


class PersistentHomologyError(ValueError):
    pass


MAX_PERSISTENCE_MOTIFS = 150


def _exact(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _value(value: Fraction) -> dict[str, str | float]:
    return {"exact": _exact(value), "decimal": float(value)}


def _open_end(*, infinite: bool, right_censored: bool) -> dict[str, Any]:
    return {
        "exact": None,
        "decimal": None,
        "infinite": infinite,
        "right_censored": right_censored,
    }


def _fraction(value: Any, label: str) -> Fraction:
    if isinstance(value, bool):
        raise PersistentHomologyError(f"{label} debe ser racional")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise PersistentHomologyError(f"{label} debe ser racional") from exc
    return result


def _validated_space(ids: Any, matrix: Any) -> tuple[list[str], list[list[Fraction]]]:
    if not isinstance(ids, list) or not 2 <= len(ids) <= MAX_PERSISTENCE_MOTIFS:
        raise PersistentHomologyError(
            f"Se necesitan entre 2 y {MAX_PERSISTENCE_MOTIFS} identificadores"
        )
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise PersistentHomologyError("Los identificadores deben ser textos únicos no vacíos")
    if not isinstance(matrix, list) or len(matrix) != len(ids):
        raise PersistentHomologyError("La matriz Dγ no tiene el tamaño esperado")
    parsed: list[list[Fraction]] = []
    for row_index, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != len(ids):
            raise PersistentHomologyError("La matriz Dγ debe ser cuadrada")
        parsed.append([
            _fraction(value, f"Dγ[{row_index},{column_index}]")
            for column_index, value in enumerate(row)
        ])
    for row in range(len(ids)):
        if parsed[row][row] != 0:
            raise PersistentHomologyError("La diagonal de Dγ debe ser cero")
        for column in range(row + 1, len(ids)):
            if parsed[row][column] < 0:
                raise PersistentHomologyError("Dγ no puede contener distancias negativas")
            if parsed[row][column] != parsed[column][row]:
                raise PersistentHomologyError("La matriz Dγ debe ser simétrica exactamente")

    order = sorted(range(len(ids)), key=lambda index: ids[index])
    canonical_ids = [ids[index] for index in order]
    canonical_matrix = [[parsed[left][right] for right in order] for left in order]
    return canonical_ids, canonical_matrix


class _UnionFind:
    def __init__(self, count: int) -> None:
        self.parent = list(range(count))
        self.members = {index: {index} for index in range(count)}

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union_elder(self, left: int, right: int) -> tuple[int, int, set[int], set[int]] | None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return None
        survivor, killed = sorted((left_root, right_root))
        survivor_members = set(self.members[survivor])
        killed_members = set(self.members[killed])
        self.parent[killed] = survivor
        self.members[survivor] |= self.members.pop(killed)
        return survivor, killed, survivor_members, killed_members


def _reduce_edges(
    edges: list[tuple[int, int, int, Fraction]], count: int
) -> tuple[set[int], dict[int, int]]:
    """Devuelve aristas positivas H1 y un ciclo generador por arista."""

    pivots: dict[int, tuple[int, int]] = {}
    positive: set[int] = set()
    generators: dict[int, int] = {}
    for edge_index, (_, left, right, _) in enumerate(edges):
        boundary = (1 << left) ^ (1 << right)
        chain = 1 << edge_index
        while boundary:
            low = boundary.bit_length() - 1
            pivot = pivots.get(low)
            if pivot is None:
                pivots[low] = (boundary, chain)
                break
            boundary ^= pivot[0]
            chain ^= pivot[1]
        if not boundary:
            positive.add(edge_index)
            generators[edge_index] = chain
    return positive, generators


def _feature_sort_key(feature: dict[str, Any]) -> tuple[Any, ...]:
    death = feature["_death"]
    persistence = feature["_persistence"]
    return (
        feature["dimension"],
        feature["_birth"],
        death is None,
        death if death is not None else Fraction(0),
        persistence is None,
        persistence if persistence is not None else Fraction(0),
        feature["_tie"],
    )


def _public_feature(feature: dict[str, Any], feature_id: str) -> dict[str, Any]:
    result = {
        "feature_id": feature_id,
        "dimension": feature["dimension"],
        "birth": _value(feature["_birth"]),
        "death": (
            _value(feature["_death"])
            | {"infinite": False, "right_censored": False}
            if feature["_death"] is not None
            else _open_end(
                infinite=feature.get("_infinite", False),
                right_censored=feature.get("_right_censored", False),
            )
        ),
        "persistence": _value(feature["_persistence"]) if feature["_persistence"] is not None else None,
        "representative_status": feature.get("representative_status", "interval_only"),
    }
    for key in ("birth_simplex", "death_simplex", "merge_certificate"):
        if key in feature:
            result[key] = feature[key]
    return result


def _selection(
    features: list[dict[str, Any]], rule: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if rule is None:
        rule = {"name": "top_k_by_persistence", "dimension": 1, "k": 10}
    if not isinstance(rule, dict):
        raise PersistentHomologyError("selection_rule debe ser un objeto")
    name = rule.get("name", "top_k_by_persistence")
    dimension = rule.get("dimension", 1)
    if dimension not in (0, 1):
        raise PersistentHomologyError("La dimensión de selección debe ser 0 o 1")
    candidates = [feature for feature in features if feature["dimension"] == dimension]
    normalized: dict[str, Any] = {"name": name, "dimension": dimension}
    if name == "all":
        selected = candidates
    elif name == "min_persistence":
        minimum = _fraction(rule.get("minimum", 0), "minimum")
        if minimum < 0:
            raise PersistentHomologyError("minimum no puede ser negativo")
        normalized["minimum"] = _exact(minimum)
        selected = [
            feature for feature in candidates
            if feature["_persistence"] is None or feature["_persistence"] >= minimum
        ]
    elif name == "top_k_by_persistence":
        k = rule.get("k", 10)
        if type(k) is not int or k < 1:
            raise PersistentHomologyError("k debe ser un entero positivo")
        normalized["k"] = k
        selected = sorted(
            candidates,
            key=lambda feature: (
                feature["_persistence"] is not None,
                feature["_persistence"] or Fraction(0),
                -feature["_birth"],
                feature["feature_id"],
            ),
            reverse=True,
        )[:k]
    else:
        raise PersistentHomologyError(
            "selection_rule.name debe ser all, min_persistence o top_k_by_persistence"
        )
    return normalized, selected


def _selected_scale(feature: dict[str, Any], rule: Any) -> tuple[dict[str, Any], Fraction | None]:
    if rule is None:
        rule = {"name": "midpoint"}
    if not isinstance(rule, dict):
        raise PersistentHomologyError("scale_rule debe ser un objeto")
    name = rule.get("name", "midpoint")
    birth, death = feature["_birth"], feature["_death"]
    if name == "midpoint":
        if death is None:
            return {"name": "midpoint", "status": "not_applicable_open_interval"}, None
        value = (birth + death) / 2
        return {"name": "midpoint"}, value
    if name == "custom_epsilon":
        value = _fraction(rule.get("epsilon"), "custom epsilon")
        if value < birth or (death is not None and value >= death):
            raise PersistentHomologyError("custom epsilon debe satisfacer birth ≤ ε < death")
        return {"name": "custom_epsilon", "epsilon": _exact(value)}, value
    raise PersistentHomologyError("scale_rule.name debe ser midpoint o custom_epsilon")


def compute_persistent_homology(
    ids: Any,
    distance_matrix_exact: Any,
    *,
    signatures: Any | None = None,
    parameters: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcula Vietoris--Rips H0/H1 con coeficientes F_2."""

    input_ids = list(ids) if isinstance(ids, list) else ids
    if signatures is not None and (
        not isinstance(signatures, list)
        or not isinstance(input_ids, list)
        or len(signatures) != len(input_ids)
        or any(not isinstance(signature, str) or not signature for signature in signatures)
    ):
        raise PersistentHomologyError("signatures debe contener una firma textual por motivo")
    signature_by_id = dict(zip(input_ids, signatures)) if signatures is not None else {}
    ids, matrix = _validated_space(ids, distance_matrix_exact)
    original_ids = list(ids)
    original_matrix = matrix
    settings = settings or {}
    if not isinstance(settings, dict):
        raise PersistentHomologyError("settings debe ser un objeto")
    unknown = set(settings) - {"max_epsilon", "selection_rule", "scale_rule", "zero_distance_mode"}
    if unknown:
        raise PersistentHomologyError(f"Opciones topológicas desconocidas: {', '.join(sorted(unknown))}")

    zero_distance_mode = settings.get("zero_distance_mode", "keep_occurrences_join_at_zero")
    if zero_distance_mode not in ("keep_occurrences_join_at_zero", "signature_quotient"):
        raise PersistentHomologyError(
            "zero_distance_mode debe ser keep_occurrences_join_at_zero o signature_quotient"
        )
    quotient_vertices = [
        {"id": identifier, "representative": identifier, "multiplicity": 1, "occurrences": [identifier]}
        for identifier in ids
    ]
    if zero_distance_mode == "signature_quotient":
        if signatures is None:
            raise PersistentHomologyError("signature_quotient requiere una firma exacta por motivo")
        grouped: dict[str, list[int]] = {}
        for index, identifier in enumerate(ids):
            grouped.setdefault(signature_by_id[identifier], []).append(index)
        groups = sorted(grouped.items(), key=lambda item: ids[item[1][0]])
        for signature, members in groups:
            for left, right in combinations(members, 2):
                if matrix[left][right] != 0:
                    raise PersistentHomologyError(
                        "Dos motivos con la misma firma no tienen distancia Dγ cero"
                    )
        for (_, left_members), (_, right_members) in combinations(groups, 2):
            expected = matrix[left_members[0]][right_members[0]]
            if any(matrix[left][right] != expected for left in left_members for right in right_members):
                raise PersistentHomologyError(
                    "Dγ no desciende consistentemente al cociente de firmas"
                )
        representative_indices = [members[0] for _, members in groups]
        quotient_vertices = [
            {
                "id": ids[members[0]],
                "representative": ids[members[0]],
                "signature": signature,
                "multiplicity": len(members),
                "occurrences": [ids[index] for index in members],
            }
            for signature, members in groups
        ]
        ids = [ids[index] for index in representative_indices]
        matrix = [
            [original_matrix[left][right] for right in representative_indices]
            for left in representative_indices
        ]

    all_distances = {Fraction(0)}
    for left in range(len(ids)):
        for right in range(left + 1, len(ids)):
            all_distances.add(matrix[left][right])
    all_scales = sorted(all_distances)
    maximum_distance = all_scales[-1]
    requested_max = settings.get("max_epsilon")
    if requested_max in (None, ""):
        maximum_used = maximum_distance
    else:
        maximum_used = _fraction(requested_max, "max_epsilon")
        if maximum_used < 0:
            raise PersistentHomologyError("max_epsilon no puede ser negativo")
        maximum_used = min(maximum_used, maximum_distance)
    truncated = maximum_used < maximum_distance
    included_scales = all_scales[:bisect_right(all_scales, maximum_used)]
    if not included_scales:
        included_scales = [Fraction(0)]
    scale_rank = {value: index for index, value in enumerate(all_scales)}
    maximum_rank = scale_rank[included_scales[-1]]

    edges = sorted(
        (
            scale_rank[matrix[left][right]],
            left,
            right,
            matrix[left][right],
        )
        for left in range(len(ids))
        for right in range(left + 1, len(ids))
        if matrix[left][right] <= maximum_used
    )
    edge_index = {(left, right): index for index, (_, left, right, _) in enumerate(edges)}
    positive_edges, generators = _reduce_edges(edges, len(ids))

    h0_internal: list[dict[str, Any]] = []
    union_find = _UnionFind(len(ids))
    for index, (rank, left, right, distance) in enumerate(edges):
        merged = union_find.union_elder(left, right)
        if merged is None:
            continue
        _, killed, survivor_members, killed_members = merged
        h0_internal.append(
            {
                "dimension": 0,
                "_birth": Fraction(0),
                "_death": distance,
                "_persistence": distance,
                "_tie": (ids[killed], ids[left], ids[right]),
                "representative_status": "merge_certificate",
                "death_simplex": {"vertices": [ids[left], ids[right]], "filtration": _value(distance)},
                "merge_certificate": {
                    "components": [
                        [ids[item] for item in sorted(survivor_members)],
                        [ids[item] for item in sorted(killed_members)],
                    ],
                    "critical_edge": {
                        "vertices": [ids[left], ids[right]],
                        "distance": _value(distance),
                    },
                },
            }
        )
    roots = sorted({union_find.find(index) for index in range(len(ids))})
    for root in roots:
        h0_internal.append(
            {
                "dimension": 0,
                "_birth": Fraction(0),
                "_death": None,
                "_persistence": None,
                "_infinite": not truncated,
                "_right_censored": truncated,
                "_tie": (ids[root],),
                "representative_status": "component",
                "merge_certificate": {
                    "component": [ids[item] for item in sorted(union_find.members[union_find.find(root)])]
                },
            }
        )

    triangles = []
    for left, middle, right in combinations(range(len(ids)), 3):
        keys = ((left, middle), (left, right), (middle, right))
        if not all(key in edge_index for key in keys):
            continue
        rank = max(edges[edge_index[key]][0] for key in keys)
        if rank <= maximum_rank:
            triangles.append((rank, left, middle, right))
    triangles.sort()

    triangle_pivots: dict[int, int] = {}
    deaths: dict[int, tuple[int, tuple[int, int, int]]] = {}
    unexpected_pivots = 0
    for rank, left, middle, right in triangles:
        column = (
            (1 << edge_index[left, middle])
            ^ (1 << edge_index[left, right])
            ^ (1 << edge_index[middle, right])
        )
        while column:
            low = column.bit_length() - 1
            pivot = triangle_pivots.get(low)
            if pivot is None:
                triangle_pivots[low] = column
                if low in positive_edges:
                    deaths[low] = (rank, (left, middle, right))
                else:
                    unexpected_pivots += 1
                break
            column ^= pivot

    h1_internal: list[dict[str, Any]] = []
    zero_h1 = 0
    for birth_edge in sorted(positive_edges):
        birth_rank, left, right, birth_value = edges[birth_edge]
        death_info = deaths.get(birth_edge)
        death_value = all_scales[death_info[0]] if death_info else None
        if death_value is not None and death_value == birth_value:
            zero_h1 += 1
            continue
        chain = generators[birth_edge]
        representative_edges = []
        for index, (_, edge_left, edge_right, distance) in enumerate(edges):
            if chain & (1 << index):
                representative_edges.append(
                    {"vertices": [ids[edge_left], ids[edge_right]], "distance": _value(distance)}
                )
        feature: dict[str, Any] = {
            "dimension": 1,
            "_birth": birth_value,
            "_death": death_value,
            "_persistence": death_value - birth_value if death_value is not None else None,
            "_infinite": death_value is None and not truncated,
            "_right_censored": death_value is None and truncated,
            "_tie": (ids[left], ids[right]),
            "representative_status": "available",
            "birth_simplex": {"vertices": [ids[left], ids[right]], "filtration": _value(birth_value)},
            "_representative": {
                "rule": "deterministic_reduced_edge_cycle_F2",
                "vertices": sorted({vertex for edge in representative_edges for vertex in edge["vertices"]}),
                "edges": representative_edges,
                "non_unique": True,
            },
        }
        if death_info:
            death_vertices = [ids[item] for item in death_info[1]]
            feature["death_simplex"] = {"vertices": death_vertices, "filtration": _value(death_value)}
        h1_internal.append(feature)

    all_internal = sorted(h0_internal + h1_internal, key=_feature_sort_key)
    counters = {0: 0, 1: 0}
    public_by_internal: dict[int, dict[str, Any]] = {}
    for feature in all_internal:
        dimension = feature["dimension"]
        counters[dimension] += 1
        feature_id = f"H{dimension}-{counters[dimension]:04d}"
        feature["feature_id"] = feature_id
        public_by_internal[id(feature)] = _public_feature(feature, feature_id)

    normalized_selection, selected = _selection(all_internal, settings.get("selection_rule"))
    scale_rule_input = settings.get("scale_rule")
    representatives: dict[str, Any] = {}
    certificates: dict[str, Any] = {}
    scale_rules: dict[str, Any] = {}
    for feature in selected:
        rule_payload, selected_scale = _selected_scale(feature, scale_rule_input)
        feature_id = feature["feature_id"]
        scale_rules[feature_id] = rule_payload
        public_by_internal[id(feature)]["selected"] = True
        if selected_scale is not None:
            public_by_internal[id(feature)]["selected_scale"] = _value(selected_scale)
        if feature["dimension"] == 1 and feature.get("_representative"):
            representative = dict(feature["_representative"])
            if selected_scale is not None:
                representative["scale"] = _value(selected_scale)
            representatives[feature_id] = representative
            certificates[feature_id] = {
                "feature_id": feature_id,
                "dimension": 1,
                "birth": _value(feature["_birth"]),
                "death": _value(feature["_death"]) if feature["_death"] is not None else None,
                "selected_scale": _value(selected_scale) if selected_scale is not None else None,
                "representative": representative,
                "edge_explanations": [
                    {
                        "vertices": edge["vertices"],
                        "distance": edge["distance"],
                        "status": "available_on_demand_via_compare",
                    }
                    for edge in representative["edges"]
                ],
                "warning": "El resumen describe este representante determinista; no es un invariante adicional de la clase.",
            }
        elif feature["dimension"] == 0 and feature.get("merge_certificate"):
            certificates[feature_id] = {
                "feature_id": feature_id,
                "dimension": 0,
                "merge": feature["merge_certificate"],
                "edge_explanation_status": "available_on_demand_via_compare",
            }

    for feature in all_internal:
        public_by_internal[id(feature)].setdefault("selected", False)

    betti_curve = []
    for scale_index, scale in enumerate(included_scales):
        betti = {}
        for dimension in (0, 1):
            living = [
                feature for feature in all_internal
                if feature["dimension"] == dimension
                and feature["_birth"] <= scale
                and (feature["_death"] is None or scale < feature["_death"])
            ]
            betti[f"beta_{dimension}"] = len(living)
        betti_curve.append(
            {
                "scale_index": scale_rank[scale],
                "epsilon": _value(scale),
                **betti,
            }
        )

    finite_h1 = [feature["_persistence"] for feature in h1_internal if feature["_persistence"] is not None]
    warnings = []
    if zero_h1:
        warnings.append(f"Se omitieron {zero_h1} intervalos H1 de persistencia nula.")
    if unexpected_pivots:
        warnings.append(f"La reducción encontró {unexpected_pivots} pivotes triangulares no generadores.")
    if any(feature["_death"] is None and not truncated for feature in h1_internal):
        warnings.append("La filtración completa dejó clases H1 esenciales; revise la reducción.")

    return {
        "protocol": "MOTIF2-persistent-homology-1.0",
        "persistent_homology": {
            "source": {
                "distance": "D_gamma",
                "profile": parameters or {},
                "item_count": len(ids),
                "original_item_count": len(original_ids),
                "canonical_item_order": ids,
                "quotient": {
                    "mode": zero_distance_mode,
                    "collapsed": len(original_ids) - len(ids),
                    "vertices": quotient_vertices,
                },
            },
            "settings": {
                "coefficient_field": 2,
                "max_homology_dimension": 1,
                "max_epsilon": _value(maximum_used),
                "full_maximum_distance": _value(maximum_distance),
                "truncated": truncated,
                "tie_break_rule": "filtration-dimension-canonical_vertex_tuple",
                "zero_distance_mode": zero_distance_mode,
            },
            "critical_scales": [
                {"index": scale_rank[scale], **_value(scale)} for scale in included_scales
            ],
            "intervals": {
                "H0": [public_by_internal[id(feature)] for feature in all_internal if feature["dimension"] == 0],
                "H1": [public_by_internal[id(feature)] for feature in all_internal if feature["dimension"] == 1],
            },
            "betti_curve": betti_curve,
            "selection": {
                "rule": normalized_selection,
                "scale_rule": scale_rule_input or {"name": "midpoint"},
                "per_feature_scale_rules": scale_rules,
                "selected_feature_ids": [feature["feature_id"] for feature in selected],
            },
            "representatives": representatives,
            "certificates": certificates,
            "summary": {
                "items": len(ids),
                "critical_scales": len(included_scales),
                "edges": len(edges),
                "triangles": len(triangles),
                "H0_intervals": len(h0_internal),
                "H1_positive_intervals": len(h1_internal),
                "H1_zero_intervals_omitted": zero_h1,
                "H1_max_persistence": _value(max(finite_h1)) if finite_h1 else None,
                "H1_mean_persistence": _value(sum(finite_h1, Fraction(0)) / len(finite_h1)) if finite_h1 else None,
                "H1_median_persistence": _value(median(finite_h1)) if finite_h1 else None,
                "selected_features": len(selected),
            },
            "warnings": warnings,
            "algorithm": {
                "name": "exact-ranked-rips-boundary-reduction",
                "version": "1.0",
                "arithmetic": "Fraction scales + integer filtration ranks + F2 bitsets",
            },
        },
    }
