"""Comparación MTI mediante asignación de coste mínimo."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any


class ComparisonError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class _LexCost:
    """Coste aditivo: distancia, eventos no emparejados y preferencia canónica."""

    primary: Fraction
    unmatched: int = 0
    canonical_preference: int = 0

    def __add__(self, other: "_LexCost") -> "_LexCost":
        return _LexCost(
            self.primary + other.primary,
            self.unmatched + other.unmatched,
            self.canonical_preference + other.canonical_preference,
        )

    def __sub__(self, other: "_LexCost") -> "_LexCost":
        return _LexCost(
            self.primary - other.primary,
            self.unmatched - other.unmatched,
            self.canonical_preference - other.canonical_preference,
        )

    def __neg__(self) -> "_LexCost":
        return _LexCost(-self.primary, -self.unmatched, -self.canonical_preference)


def _number(value: Any, name: str, *, positive: bool = False) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ComparisonError(f"El parámetro {name} no es un número válido") from exc
    if positive and result <= 0:
        raise ComparisonError(f"El parámetro {name} debe ser positivo")
    if result < 0:
        raise ComparisonError(f"El parámetro {name} no puede ser negativo")
    return result


def _descriptor(item: dict[str, Any]) -> tuple[int, Fraction, Fraction]:
    if not isinstance(item, dict) or set(item) != {"h", "u", "v"}:
        raise ComparisonError("Cada descriptor debe contener exactamente h, u y v")
    if type(item["h"]) is not int:
        raise ComparisonError("La altura h debe ser un entero")
    h = item["h"]

    def coordinate(name: str) -> Fraction:
        payload = item[name]
        if not isinstance(payload, dict) or type(payload.get("exact")) is not str:
            raise ComparisonError(f"La coordenada {name} debe incluir una fracción exacta canónica")
        text = payload["exact"]
        try:
            value = Fraction(text)
        except (ValueError, ZeroDivisionError) as exc:
            raise ComparisonError(f"La coordenada {name} no es una fracción válida") from exc
        canonical = str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
        if text != canonical:
            raise ComparisonError(f"La coordenada {name} debe estar en forma canónica ({canonical})")
        return value

    u = coordinate("u")
    v = coordinate("v")
    if not 0 <= u < v <= 1:
        raise ComparisonError("Las coordenadas normalizadas deben satisfacer 0 ≤ u < v ≤ 1")
    return h, u, v


def _validated_family(family: Any, name: str) -> list[tuple[tuple[int, Fraction, Fraction], int]]:
    if not isinstance(family, list) or not family:
        raise ComparisonError(f"La familia {name} debe ser una lista no vacía")
    indexed = [(_descriptor(item), index) for index, item in enumerate(family, start=1)]
    descriptors = [descriptor for descriptor, _ in indexed]
    if len(set(descriptors)) != len(descriptors):
        raise ComparisonError(f"La familia {name} contiene descriptores duplicados; Pmot utiliza conjuntos")
    if min(descriptor[1] for descriptor in descriptors) != 0:
        raise ComparisonError(f"La familia {name} debe contener al menos un ataque u = 0")
    if max(descriptor[2] for descriptor in descriptors) != 1:
        raise ComparisonError(f"La familia {name} debe contener al menos una terminación v = 1")
    return sorted(indexed)


def _payload(value: Fraction) -> dict[str, str | float]:
    return {
        "exact": str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}",
        "value": float(value),
    }


def _weights(parameters: dict[str, Any] | None) -> dict[str, Fraction]:
    if parameters is not None and not isinstance(parameters, dict):
        raise ComparisonError("Los parámetros deben ser un objeto")
    params = parameters or {}
    allowed_parameters = {"omega_pc", "omega_lin", "omega_on", "omega_off", "gamma"}
    unknown_parameters = set(params) - allowed_parameters
    if unknown_parameters:
        raise ComparisonError(f"Parámetros desconocidos: {', '.join(sorted(unknown_parameters))}")
    return {
        "omega_pc": _number(params.get("omega_pc", 1), "ωpc"),
        "omega_lin": _number(params.get("omega_lin", 1), "ωlin"),
        "omega_on": _number(params.get("omega_on", 1), "ωon"),
        "omega_off": _number(params.get("omega_off", 1), "ωoff"),
        "gamma": _number(params.get("gamma", 3), "γ", positive=True),
    }


def _components(
    x: tuple[int, Fraction, Fraction],
    y: tuple[int, Fraction, Fraction],
    weights: dict[str, Fraction],
) -> dict[str, Fraction]:
    h, onset, offset = x
    hp, onsetp, offsetp = y
    chromatic_delta = abs((h % 12) - (hp % 12))
    circular = min(chromatic_delta, 12 - chromatic_delta)
    height = weights["omega_pc"] * circular + weights["omega_lin"] * Fraction(abs(hp - h), 12)
    attack = weights["omega_on"] * abs(onsetp - onset)
    termination = weights["omega_off"] * abs(offsetp - offset)
    return {"height": height, "attack": attack, "termination": termination, "total": height + attack + termination}


def _hungarian(cost: list[list[Any]]) -> tuple[Any, list[int]]:
    """Algoritmo húngaro cuadrado; devuelve columna por fila."""

    n = len(cost)
    if n == 0 or any(len(row) != n for row in cost):
        raise ComparisonError("La matriz de asignación debe ser cuadrada y no vacía")
    zero = cost[0][0] - cost[0][0]
    u = [zero] * (n + 1)
    v = [zero] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        minv: list[Fraction | None] = [None] * (n + 1)
        used = [False] * (n + 1)
        j0 = 0
        while True:
            used[j0] = True
            i0 = p[j0]
            delta: Fraction | None = None
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if minv[j] is None or current < minv[j]:
                    minv[j] = current
                    way[j] = j0
                if delta is None or minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            if delta is None:
                raise ComparisonError("No existe una asignación completa")
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                elif minv[j] is not None:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [-1] * n
    for column in range(1, n + 1):
        if p[column]:
            assignment[p[column] - 1] = column - 1
    return -v[0], assignment


def compare_families_compact(
    family_a: list[dict[str, Any]],
    family_b: list[dict[str, Any]],
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcula Dγ sin materializar la explicación evento a evento.

    Una sustitución con coste mayor o igual que 2γ equivale exactamente a una
    eliminación y una inserción. Al truncar esos costes a 2γ, la asignación
    cuadrada puede reducirse de |A|+|B| a max(|A|,|B|) sin alterar Dγ.
    """

    weights = _weights(parameters)
    a = [descriptor for descriptor, _ in _validated_family(family_a, "A")]
    b = [descriptor for descriptor, _ in _validated_family(family_b, "B")]
    r, s = len(a), len(b)
    time_scale = math.lcm(
        *(coordinate.denominator for descriptor in a + b for coordinate in descriptor[1:])
    )
    cost_scale = math.lcm(
        weights["omega_pc"].denominator,
        12 * weights["omega_lin"].denominator,
        time_scale * weights["omega_on"].denominator,
        time_scale * weights["omega_off"].denominator,
        weights["gamma"].denominator,
    )
    height_pc_factor = weights["omega_pc"].numerator * (
        cost_scale // weights["omega_pc"].denominator
    )
    height_linear_factor = weights["omega_lin"].numerator * (
        cost_scale // (12 * weights["omega_lin"].denominator)
    )
    attack_factor = weights["omega_on"].numerator * (
        cost_scale // (time_scale * weights["omega_on"].denominator)
    )
    termination_factor = weights["omega_off"].numerator * (
        cost_scale // (time_scale * weights["omega_off"].denominator)
    )
    gamma = weights["gamma"].numerator * (cost_scale // weights["gamma"].denominator)
    threshold = 2 * gamma
    integer_a = [(h, int(u * time_scale), int(v * time_scale)) for h, u, v in a]
    integer_b = [(h, int(u * time_scale), int(v * time_scale)) for h, u, v in b]

    def integer_components(x: tuple[int, int, int], y: tuple[int, int, int]) -> tuple[int, int, int, int]:
        h, onset, offset = x
        hp, onsetp, offsetp = y
        chromatic_delta = abs((h % 12) - (hp % 12))
        circular = min(chromatic_delta, 12 - chromatic_delta)
        height = height_pc_factor * circular + height_linear_factor * abs(hp - h)
        attack = attack_factor * abs(onsetp - onset)
        termination = termination_factor * abs(offsetp - offset)
        return height, attack, termination, height + attack + termination

    size = max(r, s)
    matrix: list[list[int]] = []
    for i in range(size):
        row = []
        for j in range(size):
            if i < r and j < s:
                row.append(min(integer_components(integer_a[i], integer_b[j])[3], threshold))
            elif i < r or j < s:
                row.append(gamma)
            else:
                row.append(0)
        matrix.append(row)
    integer_total, assignment = _hungarian(matrix)
    total = Fraction(integer_total, cost_scale)

    matched_b = set()
    component_integers = {"height": 0, "attack": 0, "termination": 0}
    match_count = 0
    for i in range(r):
        j = assignment[i]
        parts = integer_components(integer_a[i], integer_b[j]) if j < s else None
        if parts is not None and parts[3] < threshold:
            matched_b.add(j)
            match_count += 1
            for name, value in zip(component_integers, parts[:3]):
                component_integers[name] += value
    deletion_count = r - match_count
    insertion_count = s - len(matched_b)
    component_integers["deletion"] = gamma * deletion_count
    component_integers["insertion"] = gamma * insertion_count
    if sum(component_integers.values()) != integer_total:
        raise ComparisonError("La asignación compacta produjo una descomposición inconsistente")
    component_totals = {
        name: Fraction(value, cost_scale) for name, value in component_integers.items()
    }

    empty_cost = Fraction(gamma * (r + s), cost_scale)
    dissimilarity = total / empty_cost
    return {
        "distance": _payload(total),
        "relative_index": {
            "dissimilarity": _payload(dissimilarity),
            "similarity": _payload(1 - dissimilarity),
        },
        "components": {name: _payload(value) for name, value in component_totals.items()},
    }


def compare_families(
    family_a: list[dict[str, Any]],
    family_b: list[dict[str, Any]],
    parameters: dict[str, Any] | None = None,
    *,
    cardinality_mode: str = "penalized",
) -> dict[str, Any]:
    """Calcula D_gamma y una explicación de la correspondencia óptima."""

    weights = _weights(parameters)
    if cardinality_mode not in {"penalized", "maximum_unpenalized"}:
        raise ComparisonError(f"Modo de cardinalidad desconocido: {cardinality_mode}")
    indexed_a = _validated_family(family_a, "A")
    indexed_b = _validated_family(family_b, "B")
    a = [descriptor for descriptor, _ in indexed_a]
    b = [descriptor for descriptor, _ in indexed_b]
    r, s = len(a), len(b)
    n = r + s if cardinality_mode == "penalized" else max(r, s)

    pair_costs = [[_components(x, y, weights) for y in b] for x in a]
    matrix: list[list[_LexCost]] = []
    pair_count = r * s
    large_penalized = cardinality_mode == "penalized" and pair_count > 4096
    if large_penalized:
        # Para familias grandes evitamos la matriz (r+s)^2 y los enteros de
        # desempate con r*s bits. El truncamiento a 2γ es equivalente a una
        # eliminación más una inserción y reduce la asignación a max(r,s).
        time_scale = math.lcm(
            *(coordinate.denominator for descriptor in a + b for coordinate in descriptor[1:])
        )
        cost_scale = math.lcm(
            weights["omega_pc"].denominator,
            12 * weights["omega_lin"].denominator,
            time_scale * weights["omega_on"].denominator,
            time_scale * weights["omega_off"].denominator,
            weights["gamma"].denominator,
        )
        gamma_scaled = int(weights["gamma"] * cost_scale)
        threshold = 2 * gamma_scaled
        size = max(r, s)
        for i in range(size):
            row = []
            for j in range(size):
                if i < r and j < s:
                    scaled = int(pair_costs[i][j]["total"] * cost_scale)
                    row.append(_LexCost(min(scaled, threshold), 0 if scaled <= threshold else 2, 0))
                elif i < r or j < s:
                    row.append(_LexCost(gamma_scaled, 1, 0))
                else:
                    row.append(_LexCost(0, 0, 0))
            matrix.append(row)
        lex_total, assignment = _hungarian(matrix)
        total = Fraction(lex_total.primary, cost_scale)
    else:
        for i in range(n):
            row = []
            for j in range(n):
                if i < r and j < s:
                    rank = i * s + j
                    canonical_preference = -(1 << (pair_count - rank - 1))
                    row.append(_LexCost(pair_costs[i][j]["total"], 0, canonical_preference))
                elif i < r and j >= s:
                    primary = weights["gamma"] if cardinality_mode == "penalized" else Fraction(0)
                    row.append(_LexCost(primary, 1, 0))
                elif i >= r and j < s:
                    primary = weights["gamma"] if cardinality_mode == "penalized" else Fraction(0)
                    row.append(_LexCost(primary, 1, 0))
                else:
                    row.append(_LexCost(Fraction(0), 0, 0))
            matrix.append(row)
        lex_total, assignment = _hungarian(matrix)
        total = lex_total.primary

    matched_b = set()
    matches = []
    deletions = []
    for i in range(r):
        j = assignment[i]
        substitution_allowed = j < s and (
            not large_penalized or pair_costs[i][j]["total"] <= 2 * weights["gamma"]
        )
        if substitution_allowed:
            matched_b.add(j)
            part = pair_costs[i][j]
            matches.append(
                {
                    "event_a": indexed_a[i][1],
                    "event_b": indexed_b[j][1],
                    "descriptor_a": {"h": a[i][0], "u": _payload(a[i][1]), "v": _payload(a[i][2])},
                    "descriptor_b": {"h": b[j][0], "u": _payload(b[j][1]), "v": _payload(b[j][2])},
                    "cost": {name: _payload(value) for name, value in part.items()},
                    "status": "preserved" if part["total"] == 0 else "substituted",
                }
            )
        else:
            deletion_cost = weights["gamma"] if cardinality_mode == "penalized" else Fraction(0)
            deletions.append({"event_a": indexed_a[i][1], "descriptor": {"h": a[i][0], "u": _payload(a[i][1]), "v": _payload(a[i][2])}, "cost": _payload(deletion_cost)})
    insertions = [
        {"event_b": indexed_b[j][1], "descriptor": {"h": b[j][0], "u": _payload(b[j][1]), "v": _payload(b[j][2])}, "cost": _payload(weights["gamma"] if cardinality_mode == "penalized" else Fraction(0))}
        for j in range(s)
        if j not in matched_b
    ]
    totals = {
        "height": sum((Fraction(item["cost"]["height"]["exact"]) for item in matches), Fraction(0)),
        "attack": sum((Fraction(item["cost"]["attack"]["exact"]) for item in matches), Fraction(0)),
        "termination": sum((Fraction(item["cost"]["termination"]["exact"]) for item in matches), Fraction(0)),
        "deletion": (weights["gamma"] * len(deletions)) if cardinality_mode == "penalized" else Fraction(0),
        "insertion": (weights["gamma"] * len(insertions)) if cardinality_mode == "penalized" else Fraction(0),
    }
    empty_correspondence_cost = weights["gamma"] * (r + s)
    relative_dissimilarity = total / empty_correspondence_cost
    relative_similarity = 1 - relative_dissimilarity
    exact_equivalence = a == b
    metric_status = (
        "experimental_dissimilarity"
        if cardinality_mode != "penalized"
        else "metric_profile"
        if all(weights[name] > 0 for name in ("omega_pc", "omega_lin", "omega_on", "omega_off"))
        else "pseudometric_ablation"
    )
    return {
        "metric": "D_gamma",
        "metric_status": metric_status,
        "distance_is_metric": metric_status == "metric_profile",
        "cardinality_mode": cardinality_mode,
        "distance": _payload(total),
        "equivalent": exact_equivalence,
        "zero_dissimilarity": total == 0,
        "relative_index": {
            "dissimilarity": _payload(relative_dissimilarity),
            "similarity": _payload(relative_similarity),
            "empty_correspondence_cost": _payload(empty_correspondence_cost),
            "is_metric": False,
            "applicable": cardinality_mode == "penalized",
            "bounded_0_1": cardinality_mode == "penalized",
            "separates_mti_equivalence": metric_status == "metric_profile",
        },
        "parameters": {name: _payload(value) for name, value in weights.items()},
        "matches": matches,
        "deletions": deletions,
        "insertions": insertions,
        "components": {name: _payload(value) for name, value in totals.items()},
    }
