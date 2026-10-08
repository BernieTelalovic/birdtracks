"""Focused cleanup laws, without using saved user documents as fixtures."""

from dataclasses import replace
from fractions import Fraction
import json
from unittest.mock import patch

import pytest

from birdtracks import Antisymmetriser, Connection, NodePort, Permutation, PermutationNode, Projector, ProjectorSum, Symmetriser
from birdtracks.projectors.editor import EditorState, project_port_orders
from birdtracks.projectors.editor_rewrites import cleanup_occurrences
from birdtracks.projectors.layout import default_positions
from birdtracks.projectors.simplification import collect_fully_expanded_permutations
from birdtracks.projectors.wiring import permutation_wiring_normal_form
from birdtracks.symbolic import SymbolicCoefficient


def state(p, factor=Fraction(1)):
    return EditorState.create(p, {"positions": default_positions(p), "line_colors": {}, "free_levels": {}},
                              outer_factor=factor)


def equivalent_terms():
    plain = Projector([Symmetriser((1, 2)), Antisymmetriser((2, 3, 4)), Symmetriser((1, 2))],
                      coefficient=Fraction(1, 3))
    wired = Projector([Symmetriser((1, 2)), Antisymmetriser((2, 3, 4)),
                       PermutationNode(Permutation.identity(), support=(1, 2)),
                       PermutationNode(Permutation.from_cycle(2, 3), support=(2, 3, 4)),
                       PermutationNode(Permutation.identity(), support=(2,)), Symmetriser((1, 2))],
                      coefficient=Fraction(-1, 3))
    return plain, wired


def test_collect_mixed_wiring_once_and_drop_zero_without_overwriting_first_drawing():
    plain, wired = equivalent_terms()
    zero = Projector([Symmetriser((1, 2)), Antisymmetriser((1, 2)),
                      PermutationNode(Permutation.identity(), support=(3, 4))], coefficient=Fraction(-1, 3))
    first = state(plain)
    drawing = first.presentation
    drawing["positions"]["1"] = {"x": 17, "y": 21}
    drawing["line_colors"] = {"output:0:1->left-anchor:0": "#ff0000"}
    drawing["strand_routes"] = {first.strand_ids[0]: {"0": 4}}
    first = EditorState.decode({**first.payload(), "presentation": drawing})
    inputs = (first, state(wired), state(zero))
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")), \
         patch.object(Antisymmetriser, "collapse", side_effect=AssertionError("factorial expansion")):
        result = cleanup_occurrences(inputs)
    assert len(result) == 1
    merged = result[0]
    assert merged.projector.coefficient == Fraction(2, 3)
    assert merged.outer_factor == 1
    assert merged.term_id == first.term_id
    assert merged.node_ids == first.node_ids
    assert merged.strand_ids == first.strand_ids
    assert merged.presentation == first.presentation
    assert merged.projector.collapse() == ProjectorSum(s.projector*s.outer_factor for s in inputs).collapse()
    assert EditorState.decode(json.loads(json.dumps(merged.payload()))) == merged
    assert cleanup_occurrences(result) == result


@pytest.mark.parametrize("kind", [Antisymmetriser, Symmetriser])
def test_absorption_reaches_fixed_point_across_identity_corridors(kind):
    p = Projector([kind((1, 2, 3)), PermutationNode(Permutation.identity(), support=(2, 3)),
                   kind((2, 3)), kind((2, 3))], coefficient=Fraction(-3, 7))
    before = state(p)
    with patch.object(Projector, "collapse", side_effect=AssertionError("interactive collapse")):
        (after,) = cleanup_occurrences((before,))
    assert sum(isinstance(n, kind) for n in after.projector.nodes) == 1
    assert before.node_ids[0] == after.node_ids[0]
    assert after.projector.collapse() == p.collapse()
    assert cleanup_occurrences((after,)) == (after,)


@pytest.mark.parametrize("sides", [("input",), ("output",), ("input", "output")])
def test_comparison_preserves_explicit_port_orientation_and_rational_factors(sides):
    first, wired = equivalent_terms()
    wired = project_port_orders(wired, {1: {side: (3, 2, 4) for side in sides}})
    normal = permutation_wiring_normal_form(wired)
    assert normal.collapse() == wired.collapse() == first.collapse()
    assert normal == permutation_wiring_normal_form(first)
    (merged,) = cleanup_occurrences((state(first, Fraction(-2, 5)), state(wired, Fraction(3, 7))))
    assert merged.projector.collapse() == (first * Fraction(1, 35)).collapse()


def test_symbolic_collection_and_cancellation_are_exact():
    first, wired = equivalent_terms()
    x = SymbolicCoefficient.symbol("x")
    initial = state(first, x)
    (merged,) = cleanup_occurrences((initial, state(wired, x * 2)))
    assert merged.projector is initial.projector
    assert merged.outer_factor == x * 3
    assert merged.presentation == initial.presentation
    assert not cleanup_occurrences((initial, state(wired, -x)))


def test_middle_cancellation_can_revive_first_representative():
    first, wired = equivalent_terms()
    initial = state(first)
    (merged,) = cleanup_occurrences((initial, state(wired, Fraction(-1)), state(first)))
    assert merged.term_id == initial.term_id
    assert merged.projector == initial.projector


def test_boundary_mapping_directions_and_free_strands_are_not_conflated():
    a = Antisymmetriser((1, 2))
    identity = Projector([a, PermutationNode(Permutation.identity(), support=(3, 4))])
    swapped = Projector([a, PermutationNode(Permutation.from_cycle(3, 4), support=(3, 4))])
    assert permutation_wiring_normal_form(swapped).collapse() == swapped.collapse()
    assert len(cleanup_occurrences((state(identity), state(swapped)))) == 2
    directed = Projector(identity.nodes, in_direction="left", out_direction="right")
    assert len(cleanup_occurrences((state(identity), state(directed)))) == 2


def test_closed_permutation_trace_keeps_its_dimension_factor():
    p = Projector([Antisymmetriser((2, 3)), PermutationNode(Permutation.identity(), support=(1,))],
                  [Connection(NodePort(1, 1), NodePort(1, 1))])
    assert permutation_wiring_normal_form(p) is p
    plain = Projector([Antisymmetriser((2, 3))])
    assert len(cleanup_occurrences((state(p), state(plain)))) == 2
    assert p.collapse() != plain.collapse()


def test_python_collection_uses_the_same_wiring_normalization_and_absorption():
    first, wired = equivalent_terms()
    nested = Projector([Symmetriser((5, 6, 7)), Symmetriser((6, 7)), Symmetriser((6, 7))])
    value = ProjectorSum((first, wired, nested))
    collected = collect_fully_expanded_permutations(value)
    assert len(collected) == 2
    assert collected.coefficient(Projector([Symmetriser((5, 6, 7))])) == 1
    assert collected.collapse() == value.collapse()
