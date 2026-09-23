"""One-step full-expansion simplification tests."""

from fractions import Fraction
from math import factorial

import pytest

from birdtracks import (
    Antisymmetriser,
    Connection,
    NodePort,
    PermutationNode,
    Permutation,
    Projector,
    ProjectorSum,
    Symmetriser,
    expand_node,
    permute_node_ports,
    recursive_expand_node,
    remove_multiply_connected_s_a_terms,
    simplify_step,
)
from birdtracks.projectors.simplification import collect_fully_expanded_permutations
from birdtracks.projectors.layout import _detangle_score


def test_expand_node_preserves_the_exact_operator_and_all_ports() -> None:
    projector = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((2, 3, 4))]
    )
    expanded = expand_node(projector, 1)

    assert len(expanded) == factorial(3)
    assert expanded.collapse() == projector.collapse()
    assert all(
        isinstance(term.nodes[1], PermutationNode)
        and term.nodes[1].support == frozenset({2, 3, 4})
        for term, _coefficient in expanded
    )


def test_expand_node_detangles_each_surviving_component_term() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((1, 2, 3)),
            Symmetriser((2, 3)),
        ]
    )

    expanded = expand_node(projector, 1)

    assert expanded.collapse() == projector.collapse()
    assert all(
        term.detangle().port_orders == term.port_orders
        for term, _coefficient in expanded
    )


def test_expand_node_contracts_permutation_sharing_an_operator_layer() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((3, 4)),
            Antisymmetriser((1, 2, 3, 4)),
        ]
    )

    expanded = expand_node(projector, 0)

    assert expanded.collapse() == projector.collapse()
    assert all(
        not any(isinstance(node, PermutationNode) for node in term.nodes)
        for term, _coefficient in expanded
    )


def test_detangle_ranks_wire_length_before_crossing_count() -> None:
    projector = Projector([Symmetriser((1, 2))])
    orders = {
        0: {"input": [1, 2], "output": [1, 2]},
    }

    wire_length, negative_straight, crossings = _detangle_score(projector, orders)

    assert (wire_length, negative_straight, crossings) == (4.0, -4, 0)


def test_expand_node_absorbs_every_nested_same_type_operator() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2, 3)),
            Symmetriser((1, 2)),
            Antisymmetriser((4, 5)),
        ]
    )

    expanded = expand_node(projector, 2)

    assert expanded.collapse() == projector.collapse()
    assert all(
        sum(isinstance(node, Symmetriser) for node in term.nodes) == 1
        for term, _coefficient in expanded
    )


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
def test_expand_node_collects_equal_topologies_and_adds_prefactors(
    projector_type: type,
) -> None:
    support = (1, 2, 3)
    projector = Projector(
        [
            projector_type(support),
            projector_type(support),
            projector_type(support),
        ]
    )

    expanded = expand_node(projector, 1)

    assert len(expanded) == 1
    ((term, coefficient),) = tuple(expanded)
    assert coefficient == 1
    assert expanded.collapse() == projector.collapse()
    assert term.nodes == (projector_type(support),)


def test_antisymmetriser_expansion_signs_match_each_permutation_parity() -> None:
    support = (3, 1, 2)
    expanded = expand_node(Projector([Antisymmetriser(support)]), 0)
    expected = {
        Permutation.identity(): 1,
        Permutation.from_cycle(1, 2): -1,
        Permutation.from_cycle(1, 3): -1,
        Permutation.from_cycle(2, 3): -1,
        Permutation.from_cycle(1, 2, 3): 1,
        Permutation.from_cycle(1, 3, 2): 1,
    }

    for permutation, sign in expected.items():
        term = Projector([PermutationNode(permutation, support=support)])
        assert expanded.coefficient(term) == Fraction(sign, 6)


def test_fully_expanded_permutations_collect_by_boundary_action() -> None:
    """Permutation-layer history must not survive a completed expansion."""
    layered = Projector(
        [
            PermutationNode(Permutation.from_cycle(1, 2)),
            PermutationNode(Permutation.from_cycle(2, 3)),
        ]
    )
    ((permutation, scalar),) = tuple(layered.collapse())
    direct = Projector(
        [PermutationNode(permutation, support=layered.support)]
    )
    unresolved = Projector([Symmetriser((4, 5))])
    uncollected = ProjectorSum(
        ((layered, Fraction(1, 3)), (direct, Fraction(1, 6)), unresolved)
    )

    assert len(uncollected) == 3
    collected = collect_fully_expanded_permutations(uncollected)

    assert len(collected) == 2
    term, coefficient = next(
        (term, coefficient)
        for term, coefficient in collected
        if all(isinstance(node, PermutationNode) for node in term.nodes)
    )
    assert term.nodes == (PermutationNode(permutation, support=(1, 2, 3)),)
    assert coefficient == scalar * Fraction(1, 2)
    assert collected.collapse() == uncollected.collapse()


def test_projectors_collect_across_identity_permutation_presentations() -> None:
    """An identity anchor must not distinguish the same free strand."""
    first = Projector(
        [
            Symmetriser((1, 2)),
            PermutationNode(Permutation.identity(), support=(1, 3)),
        ]
    )
    second = Projector(
        [
            Symmetriser((1, 2)),
            PermutationNode(Permutation.identity(), support=(2, 3)),
        ]
    )
    permutation = Projector(
        [PermutationNode(Permutation.from_cycle(1, 3), support=(1, 2, 3))]
    )
    value = ProjectorSum(
        ((first, Fraction(2, 9)), (permutation, Fraction(-1, 6)), (second, Fraction(4, 9)))
    )

    collected = collect_fully_expanded_permutations(value)

    assert len(value) == 3
    assert len(collected) == 2
    assert collected.coefficient(
        Projector(
            [
                Symmetriser((1, 2)),
                PermutationNode(Permutation.identity(), support=(3,)),
            ]
        )
    ) == Fraction(2, 3)
    assert collected.collapse() == value.collapse()


def test_projectors_collect_across_symmetriser_port_permutations() -> None:
    """Equivalent S/P wiring must collect with its exact prefactor."""
    permutation = PermutationNode(Permutation.from_cycle(1, 3), support=(1, 3))
    symmetriser = Symmetriser((1, 2))
    first = Projector(
        [permutation, symmetriser],
        connections=[Connection(NodePort(1, 1), NodePort(0, 1))],
        input_boundary={
            1: NodePort(1, 1),
            2: NodePort(1, 2),
            3: NodePort(0, 3),
        },
        output_boundary={
            1: NodePort(0, 1),
            2: NodePort(0, 3),
            3: NodePort(1, 2),
        },
        port_orders={
            0: {"input": (1, 3), "output": (1, 3)},
            1: {"input": (1, 2), "output": (1, 2)},
        },
    )
    second = Projector(
        [permutation, symmetriser],
        connections=first.connections,
        input_boundary=first.input_boundary,
        output_boundary={
            1: NodePort(0, 1),
            2: NodePort(1, 2),
            3: NodePort(0, 3),
        },
        port_orders={
            0: {"input": (1, 3), "output": (1, 3)},
            1: {"input": (1, 2), "output": (2, 1)},
        },
    )
    value = ProjectorSum(((first, Fraction(-4, 9)), (second, Fraction(1, 9))))

    collected = collect_fully_expanded_permutations(value)

    assert first != second
    assert first.collapse() == second.collapse()
    assert len(collected) == 1
    assert tuple(collected)[0][1] == Fraction(-1, 3)
    assert collected.collapse() == value.collapse()


def test_projectors_collect_across_different_mixed_node_shapes() -> None:
    """Permutation absorption can change a projector's displayed shape."""
    permutation = PermutationNode(Permutation.from_cycle(1, 3), support=(1, 3))
    symmetriser = Symmetriser((1, 2))
    with_permutation = Projector(
        [permutation, symmetriser],
        connections=[Connection(NodePort(1, 1), NodePort(0, 1))],
        input_boundary={
            1: NodePort(1, 1),
            2: NodePort(1, 2),
            3: NodePort(0, 3),
        },
        output_boundary={
            1: NodePort(1, 2),
            2: NodePort(0, 1),
            3: NodePort(0, 3),
        },
        port_orders={
            0: {"input": (1, 3), "output": (1, 3)},
            1: {"input": (1, 2), "output": (2, 1)},
        },
    )
    with_free_identity = Projector(
        [PermutationNode(Permutation.identity(), support=(3,)), symmetriser],
        input_boundary={
            1: NodePort(1, 1),
            2: NodePort(1, 2),
            3: NodePort(0, 3),
        },
        output_boundary={
            1: NodePort(1, 1),
            2: NodePort(0, 3),
            3: NodePort(1, 2),
        },
        port_orders={
            0: {"input": (3,), "output": (3,)},
            1: {"input": (1, 2), "output": (1, 2)},
        },
    )
    value = ProjectorSum(
        ((with_permutation, Fraction(1, 9)), (with_free_identity, Fraction(-4, 9)))
    )

    collected = collect_fully_expanded_permutations(value)

    assert with_permutation.collapse() == with_free_identity.collapse()
    assert len(collected) == 1
    assert tuple(collected)[0][1] == Fraction(-1, 3)
    assert collected.collapse() == value.collapse()


def test_full_alternating_s_a_expansion_collects_equal_permutations() -> None:
    """Regression for S(1,2)A(2,3)S(1,2)A(2,3)S(1,2)."""
    value = ProjectorSum(
        (
            Projector(
                [
                    Symmetriser((1, 2)),
                    Antisymmetriser((2, 3)),
                    Symmetriser((1, 2)),
                    Antisymmetriser((2, 3)),
                    Symmetriser((1, 2)),
                ]
            ),
        )
    )
    while True:
        next_terms = []
        expanded_any = False
        for projector, coefficient in value:
            node_index = next(
                (
                    index
                    for index, node in enumerate(projector.nodes)
                    if isinstance(node, (Symmetriser, Antisymmetriser))
                ),
                None,
            )
            if node_index is None:
                next_terms.append((projector, coefficient))
                continue
            expanded_any = True
            next_terms.extend(
                (term, coefficient * factor)
                for term, factor in expand_node(projector, node_index)
            )
        value = ProjectorSum(next_terms)
        if not expanded_any:
            break

    collected = collect_fully_expanded_permutations(value)

    assert len(value) == 8
    assert len(collected) == 6
    assert collected.collapse() == value.collapse()


def test_canvas_collects_permutation_terms_after_the_final_expansion() -> None:
    pytest.importorskip("anywidget")
    layered = Projector(
        [
            PermutationNode(Permutation.from_cycle(1, 2)),
            PermutationNode(Permutation.identity(), support=(1, 2)),
        ]
    )
    direct = Projector([Symmetriser((1, 2))])
    unresolved = Projector([Antisymmetriser((3, 4))])
    canvas = ProjectorSum(
        ((direct, 1), (layered, Fraction(1, 6)), unresolved)
    ).evaluate(detangler=False)

    selected = next(
        index
        for index, editor in enumerate(
            canvas._term_editors  # type: ignore[attr-defined]
        )
        if isinstance(editor._source_projector.nodes[0], Symmetriser)
    )
    canvas._term_editors[selected].expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "revision": 1,
    }

    value = canvas.current_projector_sum  # type: ignore[attr-defined]
    assert len(value) == 3
    assert value.coefficient(
        Projector([PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2))])
    ) == Fraction(2, 3)


def test_simplify_step_exposes_canonical_orientation_in_term_prefactors() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((1, 3)),
            Antisymmetriser((1, 2)),
        ],
        connections=[
            Connection(NodePort(1, 1), NodePort(0, 1)),
            Connection(NodePort(2, 1), NodePort(1, 1)),
            Connection(NodePort(2, 2), NodePort(0, 2)),
        ],
        input_boundary={
            1: NodePort(2, 1),
            2: NodePort(2, 2),
            3: NodePort(1, 3),
        },
        output_boundary={
            1: NodePort(0, 1),
            2: NodePort(0, 2),
            3: NodePort(1, 3),
        },
        port_orders={
            0: {"input": (1, 2), "output": (1, 2)},
            1: {"input": (1, 3), "output": (1, 3)},
            2: {"input": (1, 2), "output": (1, 2)},
        },
    )

    expanded = simplify_step(projector)

    assert len(expanded) == 1
    assert expanded.collapse() == projector.collapse()
    assert all(
        term.coefficient == 1 and coefficient == Fraction(1, 2)
        for term, coefficient in expanded
    )
    assert "Fraction(-1" not in repr(expanded)

    pytest.importorskip("anywidget")
    widget = expanded.evaluate()
    assert [
        editor.graph["term_sign"]
        for editor in widget._term_editors  # type: ignore[attr-defined]
    ] == [""]
    assert [
        editor.graph["coefficient"]
        for editor in widget._term_editors  # type: ignore[attr-defined]
    ] == [{"numerator": "1", "denominator": "2"}]
    assert widget.current_projector_sum.collapse() == expanded.collapse()  # type: ignore[attr-defined]


def test_simplify_step_applies_the_hard_zero_rule_before_expansion() -> None:
    projector = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((1, 2))]
    )

    assert simplify_step(projector) == ProjectorSum()


def test_vanishing_terms_are_removed_from_a_projector_sum() -> None:
    vanishing = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((1, 2))]
    )
    surviving = Projector([Symmetriser((1, 3))])

    assert remove_multiply_connected_s_a_terms(
        ProjectorSum((vanishing, surviving))
    ) == ProjectorSum((surviving,))


def test_simplify_step_expands_the_node_between_a_target_pair() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((2, 3)),
            Antisymmetriser((1, 3, 4)),
        ]
    )

    expanded = projector.simplify_step()

    assert len(expanded) == 1
    assert expanded.collapse() == projector.collapse()
    assert all(
        not any(isinstance(node, PermutationNode) for node in term.nodes)
        for term, _ in expanded
    )


def test_simplify_step_uses_highest_support_in_the_two_middle_layers() -> None:
    projector = Projector(
        [
            Antisymmetriser((1,)),
            Symmetriser((1, 2)),
            Antisymmetriser((2, 3, 4)),
            Symmetriser((4,)),
        ]
    )

    expanded = simplify_step(projector)

    assert expanded.collapse() == projector.collapse()
    assert all(isinstance(term.nodes[2], PermutationNode) for term, _ in expanded)


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
@pytest.mark.parametrize("side", ["input", "output"])
def test_recursive_expansion_replaces_an_embedded_node_exactly(
    projector_type: type,
    side: str,
) -> None:
    projector = Projector(
        [
            Symmetriser((1, 4)),
            projector_type((1, 2, 3)),
            Antisymmetriser((2, 4)),
        ]
    )
    reordered = permute_node_ports(projector, 1, side, 0, 2)

    expanded = recursive_expand_node(reordered, 1, side=side)

    assert reordered == projector
    assert expanded.collapse() == projector.collapse()
    assert len(expanded) <= 2


def test_recursive_expansion_preserves_selected_last_line_order() -> None:
    projector = Projector([Symmetriser((1, 2, 3))])
    reordered = permute_node_ports(projector, 0, "input", 0, 2)

    expanded = recursive_expand_node(reordered, 0, side="input")

    assert expanded.collapse() == projector.collapse()
    assert any(
        isinstance(node, Symmetriser) and node.support == {2, 3}
        for term, _coefficient in expanded
        for node in term.nodes
    )


def test_recursive_expansion_displays_both_positive_coefficients() -> None:
    projector = Projector(
        [Symmetriser((1, 2)), Symmetriser((1, 2, 3))]
    )

    expanded = recursive_expand_node(projector, 1, side="input", edge="bottom")

    assert expanded.collapse() == projector.collapse()
    pytest.importorskip("anywidget")
    widget = expanded.evaluate(detangler=False)
    assert widget.current_projector_sum.collapse() == projector.collapse()
    assert [
        editor.graph["term_sign"]
        for editor in widget._term_editors  # type: ignore[attr-defined]
    ] == ["", "+"]
    assert [
        editor.graph["coefficient"]
        for editor in widget._term_editors  # type: ignore[attr-defined]
    ] == [
        {"numerator": "2", "denominator": "3"},
        {"numerator": "1", "denominator": "3"},
    ]


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
@pytest.mark.parametrize("edge", ["top", "bottom"])
def test_recursive_expansion_renders_one_line_operators_as_free_lines(
    projector_type: type, edge: str
) -> None:
    projector = Projector([projector_type((1, 2))])

    expanded = recursive_expand_node(projector, 0, edge=edge)

    assert expanded.collapse() == projector.collapse()
    assert all(
        not isinstance(node, (Symmetriser, Antisymmetriser))
        for term, _coefficient in expanded
        for node in term.nodes
    )


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
@pytest.mark.parametrize("edge", ["top", "bottom"])
@pytest.mark.parametrize("size", [2, 3, 4, 5])
def test_recursive_edge_expansions_are_exact_and_never_leave_trivial_sa_nodes(
    projector_type: type, edge: str, size: int
) -> None:
    labels = tuple(range(1, size + 1))
    projector = Projector(
        [
            Symmetriser((1, size + 1)),
            projector_type(labels),
            Antisymmetriser((size, size + 1)),
            Symmetriser((size + 2,)),
        ]
    )

    expanded = recursive_expand_node(projector, 1, edge=edge)

    assert expanded.collapse() == projector.collapse()
    assert all(
        term.detangle().port_orders == term.port_orders
        for term, _coefficient in expanded
    )
    assert all(
        not (
            isinstance(node, (Symmetriser, Antisymmetriser))
            and len(node.support) == 1
        )
        for term, _coefficient in expanded
        for node in term.nodes
    )


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
@pytest.mark.parametrize("edge", ["top", "bottom"])
def test_two_line_recursive_expansion_is_the_full_expansion(
    projector_type: type, edge: str
) -> None:
    projector = Projector([projector_type((1, 2))])

    assert recursive_expand_node(projector, 0, edge=edge) == expand_node(
        projector, 0
    )


@pytest.mark.parametrize("projector_type", [Symmetriser, Antisymmetriser])
def test_top_recursion_peels_the_first_line_without_reordering_the_outer_node(
    projector_type: type,
) -> None:
    projector = Projector([projector_type((1, 2, 3))])

    expanded = recursive_expand_node(projector, 0, edge="top")

    assert expanded.collapse() == projector.collapse()
    assert any(
        isinstance(node, projector_type) and node.support == {2, 3}
        for term, _coefficient in expanded
        for node in term.nodes
    )
    assert any(
        isinstance(node, PermutationNode)
        and node.permutation == Permutation.from_cycle(1, 2)
        for term, _coefficient in expanded
        for node in term.nodes
    )
    assert not any(
        isinstance(node, PermutationNode)
        and node.permutation == Permutation.from_cycle(1, 3)
        for term, _coefficient in expanded
        for node in term.nodes
    )
    sandwiched = next(
        term
        for term, _coefficient in expanded
        if any(
            isinstance(node, PermutationNode)
            and node.permutation == Permutation.from_cycle(1, 2)
            for node in term.nodes
        )
    )
    assert sum(
        isinstance(node, projector_type) and node.support == {2, 3}
        for node in sandwiched.nodes
    ) == 2


def test_full_expansion_also_replaces_unrelated_trivial_sa_nodes() -> None:
    projector = Projector(
        [Symmetriser((1,)), Antisymmetriser((1, 2)), Antisymmetriser((3,))]
    )

    expanded = expand_node(projector, 1)

    assert expanded.collapse() == projector.collapse()
    assert all(
        not isinstance(node, (Symmetriser, Antisymmetriser))
        or len(node.support) > 1
        for term, _coefficient in expanded
        for node in term.nodes
    )
    assert all(
        isinstance(node, PermutationNode)
        for term, _coefficient in expanded
        for node in term.nodes
    )
