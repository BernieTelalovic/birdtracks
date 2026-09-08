"""Exact checks for named projector rewrite identities."""

from fractions import Fraction

import pytest

from birdtracks import (
    ANTISYMMETRISER_RECURSION,
    SAME_TYPE_NESTED_ABSORPTION,
    SYMMETRISER_RECURSION,
    Antisymmetriser,
    PermutationNode,
    Projector,
    Permutation,
    Symmetriser,
)


@pytest.mark.parametrize(
    ("projector_type", "identity"),
    [
        (Symmetriser, SYMMETRISER_RECURSION),
        (Antisymmetriser, ANTISYMMETRISER_RECURSION),
    ],
)
@pytest.mark.parametrize("labels", [(1, 2), (5, 1, 9), (7, 2, 8, 3)])
def test_recursive_expansion_agrees_with_exact_collapse(
    projector_type: type,
    identity: object,
    labels: tuple[int, ...],
) -> None:
    projector = Fraction(-3, 5) * Projector([projector_type(labels)])

    expanded = identity.apply(projector)

    assert expanded is not None
    assert expanded.collapse() == projector.collapse()


@pytest.mark.parametrize(
    ("projector_type", "identity"),
    [
        (Symmetriser, SYMMETRISER_RECURSION),
        (Antisymmetriser, ANTISYMMETRISER_RECURSION),
    ],
)
def test_recursive_expansion_does_not_match_fewer_than_two_lines(
    projector_type: type,
    identity: object,
) -> None:
    assert identity.apply(Projector([projector_type((4,))])) is None


@pytest.mark.parametrize(
    ("projector_type", "identity"),
    [
        (Symmetriser, SYMMETRISER_RECURSION),
        (Antisymmetriser, ANTISYMMETRISER_RECURSION),
    ],
)
def test_named_two_line_recursion_contains_no_single_line_sa(
    projector_type: type, identity: object
) -> None:
    projector = Projector([projector_type((1, 2))])

    expanded = identity.apply(projector)

    assert expanded is not None
    assert expanded.collapse() == projector.collapse()
    assert all(
        not isinstance(node, (Symmetriser, Antisymmetriser))
        for term, _coefficient in expanded
        for node in term.nodes
    )


def test_recursive_expansions_are_not_automatic_simplifications() -> None:
    projector = Projector([Symmetriser((1, 2, 3))])

    assert projector.simplify().coefficient(projector) == 1


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
@pytest.mark.parametrize("permutation_on_left", [True, False])
@pytest.mark.parametrize(
    ("permutation", "expected_sign"),
    [
        (Permutation.from_cycle(1, 3), -1),
        (Permutation.from_cycle(1, 2, 3), 1),
    ],
)
def test_supported_permutations_are_absorbed_automatically(
    projector_type: type,
    permutation_on_left: bool,
    permutation: Permutation,
    expected_sign: int,
) -> None:
    operator = Projector([projector_type((3, 1, 2, 5))])
    permutation_projector = Projector([]) * permutation
    product = (
        permutation_projector * operator
        if permutation_on_left
        else operator * permutation_projector
    )

    simplified = product.simplify()
    sign = expected_sign if projector_type is Antisymmetriser else 1

    assert simplified.coefficient(operator) == sign
    assert simplified.collapse() == product.collapse()


def test_permutation_absorption_requires_support_containment() -> None:
    operator = Projector([Symmetriser((1, 2, 3))])
    product = Permutation.from_cycle(3, 4) * operator

    assert product.simplify().coefficient(product) == 1


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
@pytest.mark.parametrize("smaller_on_left", [False, True])
def test_nested_same_type_operator_is_absorbed_on_either_side(
    projector_type: type,
    smaller_on_left: bool,
) -> None:
    bigger = projector_type((1, 2, 3))
    smaller = projector_type((1, 3))
    nodes = [smaller, bigger] if smaller_on_left else [bigger, smaller]
    projector = Fraction(-2, 5) * Projector(nodes)

    rewritten = SAME_TYPE_NESTED_ABSORPTION.apply(projector)

    assert rewritten is not None
    assert rewritten.collapse() == projector.collapse()
    ((survivor, coefficient),) = tuple(rewritten)
    assert survivor.nodes == (bigger,)
    assert coefficient == Fraction(-2, 5)


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
def test_nested_absorption_follows_lines_through_a_permutation(
    projector_type: type,
) -> None:
    projector = Projector(
        [
            projector_type((1, 2, 3)),
            PermutationNode(
                Permutation.from_cycle(1, 3), support=(1, 3)
            ),
            projector_type((1, 3)),
        ]
    )

    rewritten = SAME_TYPE_NESTED_ABSORPTION.apply(projector)

    assert rewritten is not None
    assert rewritten.collapse() == projector.collapse()
    ((survivor, coefficient),) = tuple(rewritten)
    assert survivor.nodes == projector.nodes[:2]
    assert coefficient == 1


def test_nested_antisymmetriser_absorption_preserves_port_order_sign() -> None:
    projector = Projector(
        [Antisymmetriser((1, 2, 3)), Antisymmetriser((1, 3))],
        port_orders={
            0: {"input": (1, 2, 3), "output": (1, 2, 3)},
            1: {"input": (3, 1), "output": (1, 3)},
        },
    )

    rewritten = SAME_TYPE_NESTED_ABSORPTION.apply(projector)

    assert rewritten is not None
    assert rewritten.collapse() == projector.collapse()
    ((survivor, coefficient),) = tuple(rewritten)
    assert survivor.nodes == (projector.nodes[0],)
    assert coefficient == -1
