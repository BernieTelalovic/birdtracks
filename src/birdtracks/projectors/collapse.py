"""Exact expansion of connected projector graphs into permutation sums."""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from itertools import product

from birdtracks.linear_combinations import (
    DimensionPolynomial,
    PermutationSum,
    PolynomialPermutationSum,
)
from birdtracks.permutations import Permutation

from .projector import NodePort, Projector


def collapse_projector(
    projector: Projector, *, dimension: Fraction | None = None
) -> PermutationSum | PolynomialPermutationSum:
    """Expand a projector, applying its right boundary first.

    With no explicit ``dimension``, closed loops remain exact powers of the
    symbolic variable ``N``. Supplying a value evaluates them immediately.
    """
    local_terms = tuple(tuple(node.collapse().items()) for node in projector.nodes)
    connection_target = {
        connection.source: connection.target
        for connection in projector.connections
    }
    output_label = {
        port: label for label, port in projector.output_boundary.items()
    }
    accumulator: dict[Permutation, Fraction] = {}
    symbolic: dict[Permutation, dict[int, Fraction]] = {}

    for choices in product(*local_terms):
        local_permutations = tuple(choice[0] for choice in choices)
        coefficient = projector.canonical_coefficient
        for _permutation, local_coefficient in choices:
            coefficient *= local_coefficient

        mapping, loops = _term_topology(
            projector,
            local_permutations,
            connection_target,
            output_label,
        )
        permutation = Permutation(mapping)
        if dimension is None:
            powers = symbolic.setdefault(permutation, {})
            powers[loops] = powers.get(loops, Fraction()) + coefficient
        else:
            coefficient *= dimension**loops
            accumulator[permutation] = (
                accumulator.get(permutation, Fraction()) + coefficient
            )

    if dimension is not None:
        return PermutationSum._from_accumulator(
            accumulator, line_count=len(projector.input_boundary)
        )

    polynomials = {
        permutation: DimensionPolynomial(coefficients)
        for permutation, coefficients in symbolic.items()
    }
    if all(set(polynomial.coefficients) <= {0} for polynomial in polynomials.values()):
        return PermutationSum._from_accumulator(
            {
                permutation: polynomial.coefficient(0)
                for permutation, polynomial in polynomials.items()
            },
            line_count=len(projector.input_boundary),
        )
    return PolynomialPermutationSum(polynomials)


def _term_topology(
    projector: Projector,
    local_permutations: tuple[Permutation, ...],
    connection_target: Mapping[NodePort, NodePort],
    output_label: Mapping[NodePort, int],
) -> tuple[dict[int, int], int]:
    visited: set[NodePort] = set()
    boundary_mapping: dict[int, int] = {}

    for input_label, start in projector.input_boundary.items():
        current = start
        while True:
            if current in visited:
                raise ValueError("projector wiring merges or cycles an external strand")
            visited.add(current)
            output = _local_output(current, local_permutations)
            target = connection_target.get(output)
            if target is None:
                try:
                    boundary_mapping[input_label] = output_label[output]
                except KeyError as exc:
                    raise ValueError(
                        "projector wiring reaches an unmapped external output"
                    ) from exc
                break
            current = target

    loops = 0
    all_ports = (
        NodePort(index, label)
        for index, node in enumerate(projector.nodes)
        for label in sorted(node.support)
    )
    for start in all_ports:
        if start in visited:
            continue
        current = start
        component: set[NodePort] = set()
        while current not in visited and current not in component:
            component.add(current)
            output = _local_output(current, local_permutations)
            target = connection_target.get(output)
            if target is None:
                raise ValueError("projector wiring has an unlabelled external strand")
            current = target
        visited.update(component)
        if current in component:
            loops += 1

    return boundary_mapping, loops


def _local_output(
    input_port: NodePort, local_permutations: tuple[Permutation, ...]
) -> NodePort:
    return NodePort(
        input_port.node,
        local_permutations[input_port.node](input_port.label),
    )


__all__ = ["collapse_projector"]
