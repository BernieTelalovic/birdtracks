"""Unit tests for connected symbolic projector graphs."""

from fractions import Fraction

import pytest

from birdtracks import (
    Antisymmetriser,
    Connection,
    NodePort,
    Permutation,
    PermutationNode,
    PermutationSum,
    Projector,
    ProjectorSum,
    Symmetriser,
    expand_node,
    remove_multiply_connected_s_a_terms,
)


def test_permutation_node_is_an_immutable_exact_birdtrack_node() -> None:
    permutation = Permutation.from_cycle(1, 2, 3)
    node = PermutationNode(permutation)

    assert node.support == frozenset({1, 2, 3})
    expected = PermutationSum.from_permutation(permutation)
    assert node.collapse() == expected
    assert Projector([node]).collapse() == expected


def test_permutation_node_can_retain_fixed_ambient_strands() -> None:
    node = PermutationNode(Permutation.from_cycle(1, 3), support=(1, 2, 3))

    assert node.support == frozenset({1, 2, 3})
    assert node.permutation(2) == 2
    assert Projector([node]).collapse() == node.collapse()


def test_projector_product_connects_shared_labels_and_unions_support() -> None:
    left = Projector([Symmetriser({1, 2})])
    right = Projector([Antisymmetriser({2, 3})])

    product = left * right

    assert product.nodes == left.nodes + right.nodes
    assert product.connections == (
        Connection(NodePort(1, 2), NodePort(0, 2)),
    )
    assert product.support == frozenset({1, 2, 3})
    assert set(product.output_boundary) == {1, 2, 3}
    assert product.collapse() == left.collapse() * right.collapse()


def test_permutations_multiply_projectors_in_both_orders() -> None:
    permutation = Permutation.from_cycle(1, 2)
    projector = Projector([Symmetriser({2, 3})])

    right_product = projector * permutation
    left_product = permutation * projector

    assert isinstance(right_product.nodes[-1], PermutationNode)
    assert isinstance(left_product.nodes[0], PermutationNode)
    assert set(right_product.input_boundary) == {1, 2, 3}
    assert right_product.collapse() == projector.collapse() * permutation
    assert left_product.collapse() == permutation * projector.collapse()


def test_identity_permutation_does_not_add_an_empty_node() -> None:
    projector = Projector([Symmetriser({1, 2})])

    assert projector * Permutation.identity() == projector
    assert Permutation.identity() * projector == projector


def test_projector_multiplication_is_associative_and_multiplies_coefficients() -> None:
    p = Fraction(2, 3) * Projector([Symmetriser({1, 2})])
    q = Fraction(-3, 5) * Projector([Antisymmetriser({2, 3})])
    r = Projector([PermutationNode(Permutation.from_cycle(1, 3))])

    assert (p * q) * r == p * (q * r)
    assert (p * q).coefficient == Fraction(-2, 5)


def test_simplify_promotes_an_unchanged_projector_to_a_sum() -> None:
    projector = Projector([Symmetriser({1, 2})])

    assert projector.simplify() == ProjectorSum((projector,))


def test_simplify_annihilates_a_symmetriser_antisymmetriser_double_connection() -> None:
    projector = Projector(
        [Symmetriser((1, 2, 3)), Antisymmetriser((1, 2, 4))]
    )

    assert projector.simplify() == ProjectorSum()


def test_simplify_does_not_count_connections_across_different_node_pairs() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Antisymmetriser((1, 3)),
            Antisymmetriser((2, 4)),
        ]
    )

    assert projector.simplify() == ProjectorSum((projector,))


def test_simplify_counts_s_a_connections_free_through_an_intervening_layer() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((3,)),
            Symmetriser((3, 4)),
            Symmetriser((5,)),
            Symmetriser((4, 5)),
            Antisymmetriser((1, 2)),
        ]
    )

    assert len(projector.layers) == 3
    assert projector.simplify() == ProjectorSum()


def test_simplify_follows_connections_through_an_expanded_permutation() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2)),
            Antisymmetriser((1, 2)),
        ]
    )

    assert projector.simplify() == ProjectorSum()


def test_expansion_removes_newly_double_connected_s_a_term() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((1, 3)),
            Antisymmetriser((2, 3)),
        ]
    )

    expanded = expand_node(projector, 1)
    filtered = remove_multiply_connected_s_a_terms(expanded)

    assert len(expanded) == 2
    assert len(filtered) == 1


@pytest.mark.parametrize(
    "nodes",
    [
        [Symmetriser({1}), Antisymmetriser({1}), Symmetriser({1})],
        [
            Symmetriser({1}),
            Antisymmetriser({1}),
            Antisymmetriser({1}),
            Symmetriser({1}),
        ],
    ],
)
def test_quasi_idempotent_accepts_odd_and_even_mirror_symmetry(nodes: list) -> None:
    assert Projector(nodes).quasi_idempotent()


def test_quasi_idempotent_checks_nodes_and_complete_wiring() -> None:
    asymmetric_nodes = Projector(
        [Symmetriser({1}), Antisymmetriser({1}), Antisymmetriser({1})]
    )
    asymmetric_wiring = Projector(
        [Symmetriser({1, 2}), Symmetriser({1, 2}), Symmetriser({1, 2})],
        connections=[
            Connection(NodePort(2, 1), NodePort(1, 1)),
            Connection(NodePort(2, 2), NodePort(1, 2)),
            Connection(NodePort(1, 1), NodePort(0, 2)),
            Connection(NodePort(1, 2), NodePort(0, 1)),
        ],
    )

    assert not asymmetric_nodes.quasi_idempotent()
    assert not asymmetric_wiring.quasi_idempotent()


def test_quasi_idempotent_reflects_a_permutation_to_its_inverse() -> None:
    inverse_pair = Projector(
        [
            PermutationNode(Permutation.from_cycle(1, 2, 3)),
            PermutationNode(Permutation.from_cycle(1, 3, 2)),
        ]
    )

    assert inverse_pair.quasi_idempotent()


def test_normalise_rescales_only_the_projector_prefactor() -> None:
    projector = Fraction(7, 3) * Projector([Symmetriser({1, 2})])

    normalised = projector.normalise()

    assert normalised.nodes == projector.nodes
    assert normalised.connections == projector.connections
    assert normalised.coefficient == 1
    assert normalised.collapse() * normalised.collapse() == normalised.collapse()
    assert projector.coefficient == Fraction(7, 3)


def test_normalise_rejects_an_operator_without_constant_proportionality() -> None:
    projector = Projector(
        [PermutationNode(Permutation.from_cycle(1, 2))]
    )

    with pytest.raises(ValueError, match="not a nonzero constant multiple"):
        projector.normalise()


def test_sequence_forms_maximal_disjoint_support_layers() -> None:
    projector = Projector(
        [
            Antisymmetriser({1, 4}),
            Symmetriser({2, 4}),
            Antisymmetriser({1, 3}),
            Antisymmetriser({2, 3}),
        ]
    )

    assert projector.layers == ((0,), (1, 2), (3,))


def test_matching_lines_connect_consecutive_nodes_from_right_to_left() -> None:
    projector = Projector(
        [
            Antisymmetriser({1, 4}),
            Symmetriser({2, 4}),
            Antisymmetriser({1, 3}),
            Antisymmetriser({2, 3}),
        ]
    )

    assert projector.connections == (
        Connection(NodePort(1, 4), NodePort(0, 4)),
        Connection(NodePort(2, 1), NodePort(0, 1)),
        Connection(NodePort(3, 2), NodePort(1, 2)),
        Connection(NodePort(3, 3), NodePort(2, 3)),
    )
    assert projector.external_inputs == frozenset(
        {NodePort(1, 4), NodePort(2, 1), NodePort(3, 2), NodePort(3, 3)}
    )
    assert projector.external_outputs == frozenset(
        {NodePort(0, 1), NodePort(0, 4), NodePort(1, 2), NodePort(2, 3)}
    )


def test_explicit_self_connection_represents_a_trace() -> None:
    trace = Connection(NodePort(0, 1), NodePort(0, 1))
    projector = Projector([Symmetriser({1, 2})], connections=[trace])

    assert projector.connections == (trace,)
    assert projector.external_inputs == frozenset({NodePort(0, 2)})
    assert projector.external_outputs == frozenset({NodePort(0, 2)})


def test_explicit_connections_can_join_different_supported_labels() -> None:
    connection = Connection(NodePort(1, 4), NodePort(0, 1))
    projector = Projector(
        [Symmetriser({1}), Antisymmetriser({4})],
        connections=[connection],
    )

    assert projector.connections == (connection,)


def test_a_port_cannot_have_two_connections_in_the_same_direction() -> None:
    nodes = [Symmetriser({1}), Symmetriser({1}), Symmetriser({1})]
    with pytest.raises(ValueError, match="output port"):
        Projector(
            nodes,
            connections=[
                Connection(NodePort(2, 1), NodePort(1, 1)),
                Connection(NodePort(2, 1), NodePort(0, 1)),
            ],
        )
    with pytest.raises(ValueError, match="input port"):
        Projector(
            nodes,
            connections=[
                Connection(NodePort(2, 1), NodePort(0, 1)),
                Connection(NodePort(1, 1), NodePort(0, 1)),
            ],
        )


def test_connections_must_reference_existing_supported_ports() -> None:
    with pytest.raises(ValueError, match="unknown node"):
        Projector(
            [Symmetriser({1})],
            connections=[Connection(NodePort(1, 1), NodePort(0, 1))],
        )
    with pytest.raises(ValueError, match="not supported"):
        Projector(
            [Symmetriser({1})],
            connections=[Connection(NodePort(0, 2), NodePort(0, 1))],
        )


def test_projector_scalar_arithmetic_is_exact_and_part_of_value_semantics() -> None:
    projector = Projector([Symmetriser({1, 2})])

    scaled = Fraction(-2, 3) * projector

    assert scaled.coefficient == Fraction(-2, 3)
    assert scaled != projector
    assert hash(scaled) != hash(projector)
    assert scaled / Fraction(-2, 3) == projector


def test_projector_division_by_zero_is_rejected() -> None:
    with pytest.raises(ZeroDivisionError):
        Projector([]) / 0


def test_symmetriser_boundary_reordering_is_a_canonical_equivalence() -> None:
    original = Projector([Symmetriser({1, 2})])
    rewired = Projector(
        original.nodes,
        original.connections,
        input_boundary={1: NodePort(0, 2), 2: NodePort(0, 1)},
        output_boundary=original.output_boundary,
    )

    assert rewired.input_boundary == {1: NodePort(0, 2), 2: NodePort(0, 1)}
    assert rewired == original
    assert hash(rewired) == hash(original)
    assert rewired.collapse() == original.collapse()


def test_boundary_wiring_must_cover_external_ports_exactly() -> None:
    with pytest.raises(ValueError, match="cover every external input port"):
        Projector(
            [Symmetriser({1, 2})],
            input_boundary={1: NodePort(0, 1)},
        )


def test_explicit_input_and_output_port_orders_are_immutable_state() -> None:
    projector = Projector(
        [Antisymmetriser({1, 2})],
        port_orders={0: {"input": (2, 1), "output": (1, 2)}},
    )

    assert projector.port_orders == {
        0: {"input": (2, 1), "output": (1, 2)}
    }
    assert projector.port_orders_are_explicit
    assert (projector * 2).port_orders == projector.port_orders


def test_antisymmetric_order_and_compensating_sign_compare_canonically() -> None:
    canonical = Projector([Antisymmetriser({1, 2})])
    reordered = Projector(
        canonical.nodes,
        coefficient=-1,
        port_orders={0: {"input": (2, 1), "output": (1, 2)}},
    )

    assert reordered.coefficient == -1
    assert reordered.canonical_coefficient == 1
    assert reordered == canonical
    assert hash(reordered) == hash(canonical)


def test_port_orders_must_permute_each_node_support() -> None:
    with pytest.raises(ValueError, match="must permute its support"):
        Projector(
            [Symmetriser({1, 2})],
            port_orders={0: {"input": (1, 1), "output": (1, 2)}},
        )
