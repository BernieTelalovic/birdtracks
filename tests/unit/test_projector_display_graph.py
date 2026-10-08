from birdtracks.permutations import Permutation
from birdtracks.projectors import (
    Antisymmetriser,
    PermutationNode,
    Projector,
    Symmetriser,
)
from birdtracks.projectors.display_graph import compile_display_graph


def test_pure_permutation_compiles_to_one_strand_per_boundary_line() -> None:
    projector = Projector(
        [
            PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2, 3)),
            PermutationNode(Permutation.from_cycle(2, 3), support=(1, 2, 3)),
        ]
    )

    display = compile_display_graph(projector)

    assert display.operator_columns == ()
    assert display.pure_permutation
    assert len(display.strands) == 3
    assert {strand.strand_label for strand in display.strands} == {1, 2, 3}
    assert all(strand.source.kind == "right_boundary" for strand in display.strands)
    assert all(strand.target.kind == "left_boundary" for strand in display.strands)
    assert {node for strand in display.strands for node in strand.permutation_nodes} == {
        0,
        1,
    }


def test_permutations_become_corridor_provenance_between_real_operators() -> None:
    projector = Projector(
        [
            Antisymmetriser((1, 2, 3)),
            PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2, 3)),
            Antisymmetriser((1, 2, 3)),
        ]
    )

    display = compile_display_graph(projector)

    assert display.operator_columns == ((0,), (2,))
    assert not display.pure_permutation
    middle = [
        strand
        for strand in display.strands
        if strand.source.kind == "operator_output"
        and strand.source.node == 2
        and strand.target.kind == "operator_input"
        and strand.target.node == 0
    ]
    assert len(middle) == 3
    assert all(strand.permutation_nodes == (1,) for strand in middle)


def test_hidden_permutations_do_not_prevent_disjoint_operators_sharing_column() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Antisymmetriser((3, 4)),
            PermutationNode(Permutation.identity(), support=(2,)),
            PermutationNode(Permutation.from_cycle(2, 3), support=(2, 3, 4)),
            Antisymmetriser((3, 4)),
            PermutationNode(Permutation.identity(), support=(2,)),
            Symmetriser((1, 2)),
        ]
    )

    display = compile_display_graph(projector)

    assert display.operator_columns == ((0, 1), (4, 6))


def test_display_compilation_is_deterministic_and_does_not_change_projector() -> None:
    projector = Projector(
        [PermutationNode(Permutation.from_cycle(1, 3, 2), support=(1, 2, 3))]
    )
    before = hash(projector)

    first = compile_display_graph(projector)
    second = compile_display_graph(projector)

    assert first == second
    assert first.as_dict() == second.as_dict()
    assert hash(projector) == before


def test_pure_corridor_width_is_capped_at_two_operator_footprint() -> None:
    from birdtracks.projectors.layout import widget_graph

    projector = Projector(
        [PermutationNode(Permutation.from_cycle(1, 5, 2, 4, 3), support=range(1, 6))]
    )
    graph = widget_graph(projector)
    geometry = graph["geometry"]

    assert graph["display"]["corridor_width"] <= (
        geometry["operator_width"] + geometry["layer_step"]
    )
    assert geometry["right_boundary"] == (
        geometry["left_boundary"] + graph["display"]["corridor_width"]
    )
    assert graph["display"]["corridor_width"] <= 2.4 * geometry["step"]


def test_attached_permutations_use_connector_width_without_growth() -> None:
    from birdtracks.projectors.layout import widget_graph

    graph = widget_graph(
        Projector(
            [
                Antisymmetriser((1, 2, 3, 4, 5)),
                PermutationNode(
                    Permutation.from_cycle(1, 5, 2, 4, 3), support=range(1, 6)
                ),
                Antisymmetriser((1, 2, 3, 4, 5)),
            ]
        )
    )
    widths = graph["display"]["corridor_widths"]
    step = graph["geometry"]["step"]

    assert widths == [step, step, step]


def test_boundary_permutation_adds_no_operator_column_or_padding() -> None:
    from birdtracks.projectors.layout import widget_graph, default_positions

    a = Antisymmetriser((1, 2, 3))
    swap = PermutationNode(Permutation.from_cycle(1, 3), support=(1, 2, 3))
    ordinary = widget_graph(Projector([a]))
    for nodes, index in (([a, swap], 0), ([swap, a], 1)):
        p = Projector(nodes)
        graph = widget_graph(p)
        assert graph["display"]["operator_columns"] == [[index]]
        assert graph["display"]["corridor_widths"] == ordinary["display"]["corridor_widths"]
        assert graph["geometry"]["right_boundary"] == ordinary["geometry"]["right_boundary"]
        assert default_positions(p)[str(index)] == default_positions(Projector([a]))["0"]
    pure = widget_graph(Projector([swap]))
    assert pure["display"]["corridor_width"] > ordinary["geometry"]["step"]
