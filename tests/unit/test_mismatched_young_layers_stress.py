"""Wide exact-oracle stress cases for mismatched Young-layer annihilation."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from birdtracks import (
    Antisymmetriser,
    MISMATCHED_YOUNG_LAYERS_ANNIHILATION,
    Permutation,
    PermutationNode,
    Projector,
    Symmetriser,
)


@dataclass(frozen=True)
class YoungLayerCase:
    name: str
    family: str
    order: str
    projector: Projector
    expected_rule_zero: bool
    expected_exact_zero: bool


PAIR_ORDERS = (
    ("SA-SA", ("s1", "a1", "s2", "a2")),
    ("SA-AS", ("s1", "a1", "a2", "s2")),
    ("AS-SA", ("a1", "s1", "s2", "a2")),
    ("AS-AS", ("a1", "s1", "a2", "s2")),
)


def _young_layers(
    shape: tuple[int, ...], labels: tuple[int, ...] | None = None
) -> tuple[list[object], list[object]]:
    labels = labels or tuple(range(1, sum(shape) + 1))
    if len(labels) != sum(shape):
        raise ValueError("a Young-layer label is required for every box")
    remaining = iter(labels)
    rows = tuple(
        tuple(next(remaining) for _ in range(length)) for length in shape
    )
    columns = tuple(
        tuple(row[column] for row in rows if column < len(row))
        for column in range(shape[0])
    )
    return (
        [Symmetriser(row) for row in rows if len(row) > 1],
        [Antisymmetriser(column) for column in columns if len(column) > 1],
    )


def _identity_padding(domain: tuple[int, ...], count: int = 6) -> list[object]:
    """Add horizontal depth without adding more line levels."""
    return [
        PermutationNode(Permutation.identity(), support=domain)
        for _ in range(count)
    ]


def _projector(
    first_shape: tuple[int, ...],
    second_shape: tuple[int, ...],
    order: tuple[str, ...],
    middle: list[object],
) -> Projector:
    s1, a1 = _young_layers(first_shape)
    s2, a2 = _young_layers(second_shape)
    groups = {"s1": s1, "a1": a1, "s2": s2, "a2": a2}
    nodes = [*groups[order[0]], *groups[order[1]]]
    nodes.extend(middle)
    nodes.extend((*groups[order[2]], *groups[order[3]]))
    return Projector(nodes)


def _family(
    family: str,
    first_shape: tuple[int, ...],
    second_shape: tuple[int, ...],
    middle: list[object],
    *,
    expected_rule_zero: bool,
    expected_exact_zero: bool | frozenset[str],
) -> list[YoungLayerCase]:
    return [
        YoungLayerCase(
            name=f"{family}-{order_name.lower()}",
            family=family,
            order=order_name,
            projector=_projector(first_shape, second_shape, order, middle),
            expected_rule_zero=expected_rule_zero,
            expected_exact_zero=(
                order_name in expected_exact_zero
                if isinstance(expected_exact_zero, frozenset)
                else expected_exact_zero
            ),
        )
        for order_name, order in PAIR_ORDERS
    ]


EXTRA_SA_ALL_INSIDE = (
    Symmetriser((1, 2)),
    Antisymmetriser((1, 3)),
    Symmetriser((2, 4)),
    Antisymmetriser((2, 3)),
)
EXTRA_SA_INSIDE_AND_COMPLEMENT = (
    Symmetriser((1, 2)),
    Antisymmetriser((5, 6)),
    Antisymmetriser((1, 3)),
    Symmetriser((6, 7)),
    Symmetriser((2, 4)),
    Antisymmetriser((5, 7)),
)
EXTRA_SA_INSIDE_AND_CROSSING = (
    Symmetriser((1, 2)),
    Symmetriser((1, 2, 5)),
    Antisymmetriser((1, 4)),
    Symmetriser((3, 4, 6)),
)


CASES = (
    *_family(
        "equal-size-mismatch",
        (3, 1),
        (2, 2),
        _identity_padding((1, 2, 3, 4)),
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "unequal-nonancestor",
        (2, 2),
        (3, 1, 1),
        _identity_padding((1, 2, 3, 4, 5)),
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "unequal-ancestor-control",
        (2, 1),
        (3, 1),
        _identity_padding((1, 2, 3, 4)),
        expected_rule_zero=False,
        expected_exact_zero=frozenset(("SA-SA", "AS-SA")),
    ),
    *_family(
        "equal-shape-control",
        (3, 1),
        (3, 1),
        _identity_padding((1, 2, 3, 4)),
        expected_rule_zero=False,
        expected_exact_zero=False,
    ),
    *_family(
        "internal-permutation",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            PermutationNode(
                Permutation.from_cycle(1, 2, 3), support=(1, 2, 3, 4)
            ),
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "disjoint-permutation",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            PermutationNode(Permutation.from_cycle(5, 6), support=(5, 6)),
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "partial-SA-escape-control",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            Symmetriser((1, 2, 5)),
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=False,
        expected_exact_zero=False,
    ),
    *_family(
        "extra-SA-all-inside",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            *EXTRA_SA_ALL_INSIDE,
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "extra-SA-inside-and-complement",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            *EXTRA_SA_INSIDE_AND_COMPLEMENT,
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "extra-SA-inside-and-crossing",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            *EXTRA_SA_INSIDE_AND_CROSSING,
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=False,
        expected_exact_zero=False,
    ),
    *_family(
        "partial-identity-support",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            PermutationNode(Permutation.identity(), support=(1, 5)),
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=True,
        expected_exact_zero=True,
    ),
    *_family(
        "partial-permutation-escape",
        (3, 1),
        (2, 2),
        [
            *_identity_padding((1, 2, 3, 4), 3),
            PermutationNode(Permutation.from_cycle(1, 5), support=(1, 5)),
            *_identity_padding((1, 2, 3, 4), 3),
        ],
        expected_rule_zero=False,
        expected_exact_zero=False,
    ),
)


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: case.name,
)
def test_wide_mismatched_young_layer_cases_against_exact_collapse(
    case: YoungLayerCase,
) -> None:
    rewritten = MISMATCHED_YOUNG_LAYERS_ANNIHILATION.apply(case.projector)

    assert (rewritten is not None) is case.expected_rule_zero
    assert (not case.projector.collapse()) is case.expected_exact_zero


def test_stress_cases_keep_young_pairs_outermost_and_diagrams_wide() -> None:
    for case in CASES:
        # Two Young layers on each edge plus at least six intervening layers.
        assert len(case.projector.layers) >= 10


def test_extra_sa_families_cover_domain_relationships() -> None:
    domain = frozenset((1, 2, 3, 4))

    assert all(node.support <= domain for node in EXTRA_SA_ALL_INSIDE)
    assert all(
        node.support <= domain or node.support.isdisjoint(domain)
        for node in EXTRA_SA_INSIDE_AND_COMPLEMENT
    )
    assert any(
        node.support <= domain for node in EXTRA_SA_INSIDE_AND_COMPLEMENT
    )
    assert any(
        node.support.isdisjoint(domain)
        for node in EXTRA_SA_INSIDE_AND_COMPLEMENT
    )
    assert any(
        node.support <= domain for node in EXTRA_SA_INSIDE_AND_CROSSING
    )
    assert any(
        node.support & domain
        and not node.support <= domain
        for node in EXTRA_SA_INSIDE_AND_CROSSING
    )
    for nodes in (
        EXTRA_SA_ALL_INSIDE,
        EXTRA_SA_INSIDE_AND_COMPLEMENT,
        EXTRA_SA_INSIDE_AND_CROSSING,
    ):
        assert {type(node) for node in nodes} == {Symmetriser, Antisymmetriser}


def test_stress_whiteboard_contains_every_exact_case() -> None:
    pytest.importorskip("anywidget")
    from birdtracks import whiteboard

    path = (
        Path(__file__).parents[2]
        / "examples"
        / "whiteboard"
        / "mismatched-young-layers.whiteboard"
    )
    document = whiteboard(path, debug=True)

    assert len(document.embedded_projectors) == len(CASES)
    assert all(
        editor.projector == case.projector
        for editor, case in zip(document.embedded_projectors, CASES, strict=True)
    )
