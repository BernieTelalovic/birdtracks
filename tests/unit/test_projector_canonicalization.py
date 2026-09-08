"""Canonical equality under internal strand presentation changes."""

from fractions import Fraction

import pytest

from birdtracks import (
    Antisymmetriser,
    Connection,
    NodePort,
    Permutation,
    PermutationNode,
    Projector,
    Symmetriser,
)


def test_dummy_labels_are_ignored_while_boundary_labels_remain_fixed() -> None:
    first = Projector(
        [Symmetriser((1, 2)), Symmetriser((3, 4))],
        connections=[
            Connection(NodePort(1, 3), NodePort(0, 1)),
            Connection(NodePort(1, 4), NodePort(0, 2)),
        ],
    )
    renamed = Projector(
        [Symmetriser((20, 10)), Symmetriser((3, 4))],
        connections=[
            Connection(NodePort(1, 3), NodePort(0, 20)),
            Connection(NodePort(1, 4), NodePort(0, 10)),
        ],
    )

    assert first == renamed
    assert hash(first) == hash(renamed)
    assert first.collapse() == renamed.collapse()


def test_disjoint_nodes_are_independent_of_sequence_order() -> None:
    first = Projector([Symmetriser((1,)), Antisymmetriser((2,))])
    reordered = Projector([Antisymmetriser((2,)), Symmetriser((1,))])

    assert first == reordered
    assert hash(first) == hash(reordered)


def test_internal_antisymmetric_reordering_canonicalizes_with_its_sign() -> None:
    straight = Projector(
        [Antisymmetriser((1, 2)), Antisymmetriser((1, 2))]
    )
    reordered = Projector(
        [Antisymmetriser((1, 2)), Antisymmetriser((1, 2))],
        connections=[
            Connection(NodePort(1, 1), NodePort(0, 2)),
            Connection(NodePort(1, 2), NodePort(0, 1)),
        ],
    )

    assert straight == reordered
    assert hash(straight) == hash(reordered)
    assert straight.collapse() == reordered.collapse()


def test_absorbable_permutations_share_the_projector_canonical_form() -> None:
    permutation = Permutation.from_cycle(1, 3)
    symmetriser = Projector([Symmetriser((3, 1, 2))])
    antisymmetriser = Projector([Antisymmetriser((3, 1, 2))])

    assert permutation * symmetriser == symmetriser
    assert symmetriser * permutation == symmetriser
    assert permutation * antisymmetriser == -antisymmetriser
    assert antisymmetriser * permutation == -antisymmetriser


def test_crossed_wiring_is_not_absorbed_without_its_orientation_sign() -> None:
    permutation = Permutation.from_cycle(1, 2)
    nodes = [
        PermutationNode(permutation, support=(1, 2)),
        Antisymmetriser((1, 2)),
    ]
    boundaries = {
        "input_boundary": {1: NodePort(1, 1), 2: NodePort(1, 2)},
        "output_boundary": {1: NodePort(0, 1), 2: NodePort(0, 2)},
    }
    straight = Projector(
        nodes,
        connections=[
            Connection(NodePort(1, 1), NodePort(0, 1)),
            Connection(NodePort(1, 2), NodePort(0, 2)),
        ],
        **boundaries,
    )
    crossed = Projector(
        nodes,
        connections=[
            Connection(NodePort(1, 1), NodePort(0, 2)),
            Connection(NodePort(1, 2), NodePort(0, 1)),
        ],
        **boundaries,
    )
    relabelled_boundary = Projector(
        nodes,
        connections=straight.connections,
        input_boundary={1: NodePort(1, 2), 2: NodePort(1, 1)},
        output_boundary=boundaries["output_boundary"],
    )

    assert straight != crossed
    assert straight.collapse() != crossed.collapse()
    assert straight != relabelled_boundary
    assert straight.collapse() != relabelled_boundary.collapse()


def test_symmetriser_equivalent_internal_routings_are_canonical() -> None:
    first = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((2, 3)), Symmetriser((1, 2))],
        connections=[
            Connection(NodePort(1, 2), NodePort(0, 2)),
            Connection(NodePort(2, 1), NodePort(0, 1)),
            Connection(NodePort(2, 2), NodePort(1, 2)),
        ],
        coefficient=Fraction(4, 3),
        input_boundary={1: NodePort(2, 1), 2: NodePort(2, 2), 3: NodePort(1, 3)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 3)},
        port_orders={
            0: {"input": (1, 2), "output": (1, 2)},
            1: {"input": (2, 3), "output": (2, 3)},
            2: {"input": (1, 2), "output": (1, 2)},
        },
    )
    second = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((1, 3)), Symmetriser((1, 2))],
        connections=[
            Connection(NodePort(1, 1), NodePort(0, 1)),
            Connection(NodePort(2, 1), NodePort(1, 1)),
            Connection(NodePort(2, 2), NodePort(0, 2)),
        ],
        coefficient=Fraction(4, 3),
        input_boundary={1: NodePort(2, 1), 2: NodePort(2, 2), 3: NodePort(1, 3)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2), 3: NodePort(1, 3)},
        port_orders={
            0: {"input": (1, 2), "output": (1, 2)},
            1: {"input": (1, 3), "output": (1, 3)},
            2: {"input": (1, 2), "output": (1, 2)},
        },
    )

    assert first.collapse() == second.collapse()
    assert first == second
    assert hash(first) == hash(second)


def test_modulo_compares_projectors_up_to_nonzero_scalar() -> None:
    projector = Fraction(4, 3) * Projector([Antisymmetriser((3, 1, 2))])
    equivalent = Fraction(4, 3) * Projector([Antisymmetriser((1, 2, 3))])

    assert projector % equivalent
    assert projector % -equivalent
    assert projector % (2 * equivalent)
    assert projector % (Fraction(-17, 5) * equivalent)
    assert not projector % Projector([Symmetriser((1, 2, 3))])


def test_modulo_handles_zero_projectors_literally() -> None:
    zero_s = 0 * Projector([Symmetriser((1, 2))])
    zero_a = 0 * Projector([Antisymmetriser((3, 4))])
    nonzero = Projector([Symmetriser((1, 2))])

    assert zero_s % zero_a
    assert not zero_s % nonzero
    assert not nonzero % zero_s


def test_modulo_rejects_non_projector_operands() -> None:
    projector = Projector([Symmetriser((1, 2))])

    with pytest.raises(TypeError, match="unsupported operand"):
        _ = projector % 1
