import pytest

import birdtracks as bt
from birdtracks import representations


@pytest.fixture
def backend():
    return representations.pair_backend()


def test_constructs_from_row_and_column_words(backend):
    diagram = backend.YoungDiagram((2, 1))
    expected = bt.Tableau(((1, 3), (2,)))

    assert bt.tableau(diagram, row_word=(1, 3, 2)) == expected
    assert bt.tableau(diagram, column_word=(1, 2, 3)) == expected
    assert expected.row_word == (1, 3, 2)
    assert expected.column_word == (1, 2, 3)
    assert expected.partition == (2, 1)


def test_barred_diagram_and_one_sided_pairs_preserve_orientation(backend):
    barred = backend.YoungDiagram((2, 1), barred=True)
    barred_pair = backend.Pair(((2, 1), ()))
    unbarred_pair = backend.Pair(((), (2, 1)))

    assert bt.tableau(barred, row_word=(1, 2, 3)).barred
    assert bt.tableau(barred_pair, row_word=(1, 2, 3)).barred
    assert not bt.tableau(unbarred_pair, row_word=(1, 2, 3)).barred


def test_enumerates_all_standard_tableaux_deterministically(backend):
    diagram = backend.YoungDiagram((2, 1))
    assert bt.standard_tableaux(diagram) == (
        bt.Tableau(((1, 2), (3,))),
        bt.Tableau(((1, 3), (2,))),
    )
    assert bt.standard_tableaux(backend.YoungDiagram(())) == (bt.Tableau(()),)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "exactly one"),
        ({"row_word": (1,), "column_word": (1,)}, "exactly one"),
        ({"row_word": (1, 1, 3)}, "exactly the integers"),
        ({"row_word": (2, 1, 3)}, "increase across rows"),
    ],
)
def test_rejects_invalid_words(backend, kwargs, message):
    with pytest.raises(ValueError, match=message):
        bt.tableau(backend.YoungDiagram((2, 1)), **kwargs)


def test_rejects_two_sided_and_empty_pairs(backend):
    with pytest.raises(ValueError, match="only one nonempty part"):
        bt.tableau(backend.Pair(((1,), (1,))), row_word=(1,))
    with pytest.raises(ValueError, match="one nonempty part"):
        bt.standard_tableaux(backend.Pair(((), ())))


def test_mold_projector_uses_the_compact_palindromic_construction(backend):
    value = bt.tableau(backend.YoungDiagram((3, 2)), row_word=(1, 2, 4, 3, 5))
    projector = bt.mold_projector(value)
    collapsed = projector.collapse()

    assert all(
        collapsed.coefficient(permutation.inverse()) == coefficient
        for permutation, coefficient in collapsed.items()
    )
    assert projector.coefficient == 4


def test_mold_projectors_are_orthogonal_for_equal_shapes(backend):
    tableaux = bt.standard_tableaux(backend.YoungDiagram((2, 1)))
    first, second = map(bt.mold_projector, tableaux)

    assert not (first * second).collapse()
    assert not (second * first).collapse()


def test_mold_projector_handles_column_order_and_barred_tableaux(backend):
    value = bt.tableau(
        backend.YoungDiagram((2, 2), barred=True), column_word=(1, 2, 3, 4)
    )
    projector = bt.mold_projector(value)

    assert projector.in_direction == "neutral"
    assert projector.out_direction == "neutral"
    assert (projector * projector).collapse() == projector.collapse()


def test_mold_projector_rejects_non_tableaux():
    with pytest.raises(TypeError, match="expects a Tableau"):
        bt.mold_projector(object())
