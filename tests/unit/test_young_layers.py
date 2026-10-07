"""Tests for recognizing repeated adjacent Young S/A layers."""

from birdtracks import Antisymmetriser, Projector, Symmetriser


def test_identify_largest_young_layer_pair_in_either_order() -> None:
    projector = Projector([
        Antisymmetriser((1, 4)),
        Antisymmetriser((2, 5)),
        Symmetriser((1, 2, 3)),
        Symmetriser((4, 5)),
    ])

    match = projector.identify_largest_young_layer_pair()

    assert match is not None
    assert match.shape == (3, 2)
    assert match.support == frozenset({1, 2, 3, 4, 5})
    assert match.layers == (0, 1)
    assert match.order == "AS"


def test_largest_pair_returns_none_for_incomplete_incidence() -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((3, 4)),
        Antisymmetriser((1, 3)),
        Antisymmetriser((2, 5)),
    ])

    assert projector.identify_largest_young_layer_pair() is None


def test_largest_pair_is_ranked_by_support_size() -> None:
    projector = Projector([
        Symmetriser((8, 9)),
        Antisymmetriser((8, 10)),
        Symmetriser((1, 2, 3)),
        Symmetriser((4, 5)),
        Antisymmetriser((1, 4)),
        Antisymmetriser((2, 5)),
    ])

    match = projector.identify_largest_young_layer_pair()

    assert match is not None
    assert match.shape == (3, 2)
    assert match.support == frozenset({1, 2, 3, 4, 5})
    assert match.layers == (1, 2)


def test_identify_bracketing_young_layers_with_subset_supported_middle() -> None:
    projector = Projector([
        Symmetriser((1, 2, 3)),
        Symmetriser((4, 5)),
        Antisymmetriser((1, 4)),
        Antisymmetriser((2, 5)),
        Symmetriser((1, 2)),
        Antisymmetriser((1, 4)),
        Antisymmetriser((2, 5)),
        Symmetriser((1, 2, 3)),
        Symmetriser((4, 5)),
    ])

    match = projector.identify_bracketing_young_layers()

    assert match is not None
    assert match.shape == (3, 2)
    assert match.support == frozenset({1, 2, 3, 4, 5})
    assert match.layers == ((0, 1), (3, 4))
    assert tuple(item.order for item in match.occurrences) == ("SA", "AS")


def test_bracketing_rejects_middle_sa_support_outside_domain() -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Antisymmetriser((1, 3)),
        Symmetriser((1, 9)),
        Antisymmetriser((1, 3)),
        Symmetriser((1, 2)),
    ])

    assert projector.identify_bracketing_young_layers() is None
