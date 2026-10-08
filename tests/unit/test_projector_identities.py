"""Exact checks for named projector rewrite identities."""

from fractions import Fraction

import pytest

from birdtracks import (
    ANTISYMMETRISER_RECURSION,
    MISMATCHED_YOUNG_LAYERS_ANNIHILATION,
    SAME_TYPE_NESTED_ABSORPTION,
    SYMMETRISER_RECURSION,
    Antisymmetriser,
    PermutationNode,
    Projector,
    ProjectorSum,
    Permutation,
    Symmetriser,
    recursive_expand_node,
)
from birdtracks.settings import SIMPLIFICATION_RULES


def _young_layers(
    shape: tuple[int, ...], offset: int = 0
) -> tuple[list[object], list[object]]:
    rows: list[tuple[int, ...]] = []
    next_label = offset + 1
    for length in shape:
        rows.append(tuple(range(next_label, next_label + length)))
        next_label += length
    return _young_layers_from_rows(tuple(rows))


def _young_layers_from_rows(
    rows: tuple[tuple[int, ...], ...],
) -> tuple[list[object], list[object]]:
    columns = tuple(
        tuple(row[column] for row in rows if column < len(row))
        for column in range(len(rows[0]))
    )
    return (
        [Symmetriser(row) for row in rows if len(row) > 1],
        [Antisymmetriser(column) for column in columns if len(column) > 1],
    )


PAIR_ORDERS = (
    ("s1", "a1", "s2", "a2"),
    ("s1", "a1", "a2", "s2"),
    ("a1", "s1", "s2", "a2"),
    ("a1", "s1", "a2", "s2"),
)


def _identity_witnesses() -> dict[str, Projector]:
    first_rows, first_columns = _young_layers((3, 1))
    second_rows, second_columns = _young_layers((2, 2))
    permutation = Projector([]) * Permutation.from_cycle(1, 2)
    symmetriser = Projector([Symmetriser((1, 2, 3))])
    antisymmetriser = Projector([Antisymmetriser((1, 2, 3))])
    return {
        "multiply_connected_symmetriser_antisymmetriser_annihilation": Projector(
            [Symmetriser((1, 2)), Antisymmetriser((1, 2))]
        ),
        "mismatched_young_layers_annihilation": Projector(
            (*first_rows, *first_columns, *second_rows, *second_columns)
        ),
        "same_type_nested_absorption": Projector(
            [Symmetriser((1, 2, 3)), Symmetriser((1, 2))]
        ),
        "symmetriser_recursion": symmetriser,
        "antisymmetriser_recursion": antisymmetriser,
        "permutation_left_symmetriser_absorption": permutation * symmetriser,
        "permutation_right_symmetriser_absorption": symmetriser * permutation,
        "permutation_left_antisymmetriser_absorption": (
            permutation * antisymmetriser
        ),
        "permutation_right_antisymmetriser_absorption": (
            antisymmetriser * permutation
        ),
    }


def test_every_algebraic_identity_is_listed_and_enabled() -> None:
    from birdtracks import IDENTITIES

    assert set(SIMPLIFICATION_RULES) == set(IDENTITIES)
    assert all(SIMPLIFICATION_RULES.values())


@pytest.mark.parametrize("name", tuple(SIMPLIFICATION_RULES))
def test_every_enabled_algebraic_identity_is_applied(name: str) -> None:
    from birdtracks import IDENTITIES

    assert IDENTITIES[name].apply(_identity_witnesses()[name]) is not None


@pytest.mark.parametrize("name", tuple(SIMPLIFICATION_RULES))
def test_disabled_algebraic_identity_is_not_applied(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from birdtracks import IDENTITIES

    monkeypatch.setitem(SIMPLIFICATION_RULES, name, False)

    assert IDENTITIES[name].apply(_identity_witnesses()[name]) is None


@pytest.mark.parametrize(
    ("name", "node"),
    [
        ("symmetriser_recursion", Symmetriser((1, 2, 3))),
        ("antisymmetriser_recursion", Antisymmetriser((1, 2, 3))),
    ],
)
def test_disabled_recursion_is_not_used_by_recursive_simplification(
    name: str, node: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    projector = Projector([node])
    monkeypatch.setitem(SIMPLIFICATION_RULES, name, False)

    assert recursive_expand_node(projector, 0) == ProjectorSum((projector,))


@pytest.mark.parametrize(
    "order",
    PAIR_ORDERS,
)
def test_different_young_layer_shapes_annihilate_in_any_order(
    order: tuple[str, ...],
) -> None:
    s1, a1 = _young_layers((3, 1))
    s2, a2 = _young_layers((2, 2))
    groups = {"s1": s1, "a1": a1, "s2": s2, "a2": a2}
    projector = Projector(node for key in order for node in groups[key])

    assert (
        MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector)
        == projector.simplify()
    )
    assert not projector.simplify()
    assert not projector.collapse()


def test_crossing_young_layer_pairs_do_not_trigger_annihilation() -> None:
    s1, a1 = _young_layers((3, 1))
    s2, a2 = _young_layers((2, 2))
    projector = Projector((*s1, *a2, *a1, *s2))

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None


def test_nested_young_layer_pairs_do_not_trigger_annihilation() -> None:
    s1, a1 = _young_layers((3, 1))
    s2, a2 = _young_layers((2, 2))
    projector = Projector((*s1, *s2, *a2, *a1))

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None


def test_equal_young_layer_shapes_do_not_annihilate() -> None:
    s1, a1 = _young_layers((3, 1))
    s2, a2 = _young_layers((3, 1))
    projector = Projector((*s1, *a1, *s2, *a2))

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None


@pytest.mark.parametrize(
    "order",
    PAIR_ORDERS,
)
def test_unequal_ancestor_young_shapes_do_not_annihilate(
    order: tuple[str, ...],
) -> None:
    s1, a1 = _young_layers_from_rows(((1, 2), (3,)))
    s2, a2 = _young_layers_from_rows(((1, 2, 4), (3,)))
    groups = {"s1": s1, "a1": a1, "s2": s2, "a2": a2}
    projector = Projector(node for key in order for node in groups[key])

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None
    assert projector.collapse()


@pytest.mark.parametrize(
    "order",
    PAIR_ORDERS,
)
def test_unequal_nonancestor_young_shapes_annihilate(
    order: tuple[str, ...],
) -> None:
    s1, a1 = _young_layers((2, 2))
    s2, a2 = _young_layers((3, 1, 1))
    groups = {"s1": s1, "a1": a1, "s2": s2, "a2": a2}
    projector = Projector(node for key in order for node in groups[key])

    rewritten = MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector)
    assert rewritten is not None
    assert not rewritten
    assert not projector.collapse()


@pytest.mark.parametrize("order", PAIR_ORDERS)
@pytest.mark.parametrize("gap", range(3))
@pytest.mark.parametrize("escaping_type", [Symmetriser, Antisymmetriser])
def test_unequal_young_layer_rule_rejects_escape_from_larger_domain(
    order: tuple[str, ...],
    gap: int,
    escaping_type: type,
) -> None:
    s1, a1 = _young_layers((2, 2))
    s2, a2 = _young_layers((3, 1, 1))
    groups = {"s1": s1, "a1": a1, "s2": s2, "a2": a2}
    layers = [groups[key] for key in order]
    layers[gap + 1] = [escaping_type((1, 2, 6)), *layers[gap + 1]]
    projector = Projector(node for layer in layers for node in layer)

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None


def test_young_layer_rule_requires_nested_domains() -> None:
    s1, a1 = _young_layers((2, 2))
    s2, a2 = _young_layers((3, 1, 1), offset=2)
    projector = Projector((*s1, *a1, *s2, *a2))

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None


@pytest.mark.parametrize(
    "order",
    PAIR_ORDERS,
)
@pytest.mark.parametrize("gap", range(3))
@pytest.mark.parametrize("escaping_type", [Symmetriser, Antisymmetriser])
def test_young_layer_rule_rejects_an_operator_escaping_the_shared_domain(
    order: tuple[str, ...],
    gap: int,
    escaping_type: type,
) -> None:
    s1, a1 = _young_layers((3, 1))
    s2, a2 = _young_layers((2, 2))
    groups = {"s1": s1, "a1": a1, "s2": s2, "a2": a2}
    layers = [groups[key] for key in order]
    layers[gap + 1] = [escaping_type((1, 2, 5)), *layers[gap + 1]]
    projector = Projector(node for layer in layers for node in layer)

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) is None


@pytest.mark.parametrize(
    ("first_shape", "second_shape"),
    [
        ((3, 1), (2, 2)),
        ((2, 2), (3, 1, 1)),
    ],
)
def test_young_layer_rule_allows_disjoint_tensor_factors_and_intervening_nodes(
    first_shape: tuple[int, ...],
    second_shape: tuple[int, ...],
) -> None:
    s1, a1 = _young_layers(first_shape)
    s2, a2 = _young_layers(second_shape)
    projector = Projector(
        (
            Symmetriser((10, 11)),
            *s1,
            *a1,
            Antisymmetriser((12, 13)),
            *s2,
            *a2,
            Symmetriser((14, 15)),
        )
    )

    assert MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(projector) == ProjectorSum()


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
