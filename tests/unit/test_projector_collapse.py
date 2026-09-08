"""Exact collapse tests for connected projector graphs."""

from fractions import Fraction

import pytest

from birdtracks import (
    Antisymmetriser,
    Connection,
    DimensionPolynomial,
    NodePort,
    Permutation,
    PermutationSum,
    Projector,
    PolynomialPermutationSum,
    Symmetriser,
)


def test_single_node_projector_collapse_matches_node_collapse() -> None:
    node = Symmetriser({1, 2, 4})

    assert Projector([node]).collapse() == node.collapse()


def test_right_to_left_composition_of_matching_projectors_is_exact() -> None:
    node = Symmetriser({1, 2})
    projector = Projector([node, node])

    assert projector.collapse() == node.collapse()


def test_symmetriser_after_antisymmetriser_collapses_to_zero() -> None:
    projector = Projector(
        [Symmetriser({1, 2}), Antisymmetriser({1, 2})]
    )

    assert projector.collapse() == PermutationSum.zero()


def test_boundary_wiring_is_applied_to_collapsed_permutations() -> None:
    node = Antisymmetriser({1, 2})
    projector = Projector(
        [node],
        input_boundary={1: NodePort(0, 2), 2: NodePort(0, 1)},
    )

    assert projector.collapse() == -node.collapse()


def test_trace_contributes_one_exact_dimension_factor() -> None:
    projector = Projector(
        [Symmetriser({1, 2})],
        connections=[Connection(NodePort(0, 1), NodePort(0, 1))],
    )
    identity = Permutation.identity()

    assert projector.collapse(dimension=3) == Fraction(2) * identity
    assert projector.collapse(dimension=Fraction(5, 2)) == (
        Fraction(7, 4) * identity
    )


def test_trace_without_dimension_returns_exact_polynomial() -> None:
    projector = Projector(
        [Symmetriser({1, 2})],
        connections=[Connection(NodePort(0, 1), NodePort(0, 1))],
    )

    collapsed = projector.collapse()

    assert isinstance(collapsed, PolynomialPermutationSum)
    assert collapsed.coefficient(Permutation.identity()) == DimensionPolynomial(
        {0: Fraction(1, 2), 1: Fraction(1, 2)}
    )
    assert collapsed.evaluate(3) == projector.collapse(dimension=3)


def test_collapsed_projector_retains_lines_for_later_trace() -> None:
    collapsed = Projector([Symmetriser((1, 2))]).collapse()

    assert isinstance(collapsed, PermutationSum)
    assert collapsed.line_count == 2
    assert collapsed.trace() == DimensionPolynomial(
        {1: Fraction(1, 2), 2: Fraction(1, 2)}
    )
    assert collapsed.trace(domain_size=4) == DimensionPolynomial(
        {3: Fraction(1, 2), 4: Fraction(1, 2)}
    )
    with pytest.raises(ValueError, match=r"retained line count \(2\)"):
        collapsed.trace(domain_size=1)
    assert (2 * collapsed).line_count == 2
    assert (collapsed * Permutation.identity()).line_count == 2


def test_permutation_sum_without_projector_provenance_rejects_trace() -> None:
    value = PermutationSum.from_permutation(Permutation.identity())

    assert value.trace(domain_size=3) == DimensionPolynomial({3: 1})
    with pytest.raises(ValueError, match="domain_size or"):
        value.trace()


def test_empty_projector_collapses_to_identity() -> None:
    assert Projector([]).collapse() == PermutationSum.from_permutation(
        Permutation.identity()
    )


def test_saved_antisymmetric_port_order_uses_canonical_coefficient() -> None:
    node = Antisymmetriser({1, 2})
    reordered = Projector(
        [node],
        coefficient=-1,
        port_orders={0: {"input": (2, 1), "output": (1, 2)}},
    )

    assert reordered.collapse() == node.collapse()


def test_multiple_closed_loops_contribute_a_dimension_power() -> None:
    projector = Projector(
        [Symmetriser({1}), Symmetriser({2})],
        connections=[
            Connection(NodePort(0, 1), NodePort(0, 1)),
            Connection(NodePort(1, 2), NodePort(1, 2)),
        ],
    )

    assert projector.collapse(dimension=3) == 9 * Permutation.identity()


def test_trace_closes_matching_left_and_right_boundaries() -> None:
    projector = Projector([Symmetriser({1, 2})])

    traced = projector.trace()

    assert traced.connections == (
        Connection(NodePort(0, 1), NodePort(0, 1)),
        Connection(NodePort(0, 2), NodePort(0, 2)),
    )
    assert not traced.external_inputs
    assert not traced.external_outputs
    assert traced.collapse(dimension=3) == 6 * Permutation.identity()
    symbolic = traced.collapse()
    assert isinstance(symbolic, PolynomialPermutationSum)
    assert symbolic.coefficient(Permutation.identity()) == DimensionPolynomial(
        {1: Fraction(1, 2), 2: Fraction(1, 2)}
    )


def test_trace_uses_saved_boundary_identification() -> None:
    projector = Projector(
        [Antisymmetriser({1, 2})],
        input_boundary={1: NodePort(0, 2), 2: NodePort(0, 1)},
    )

    assert projector.trace().connections == (
        Connection(NodePort(0, 1), NodePort(0, 2)),
        Connection(NodePort(0, 2), NodePort(0, 1)),
    )


def test_trace_of_closed_projector_is_idempotent() -> None:
    traced = Projector([Symmetriser({1})]).trace()

    assert traced.trace() is traced
