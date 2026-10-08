import os
from itertools import permutations
from pathlib import Path
import shutil
import subprocess

import pytest

from birdtracks import (
    Antisymmetriser,
    Permutation,
    PermutationNode,
    Projector,
    Symmetriser,
)
from birdtracks.projectors.layout import default_positions, widget_graph
from birdtracks.projectors.whiteboard.latex import whiteboard_latex


def test_pair_export_preserves_term_content_and_cell_style() -> None:
    pair = {
        "pair_expression": {
            "version": 1,
            "kind": "sum",
            "terms": [{
                "kind": "pair",
                "barred": [1],
                "unbarred": [1],
                "coefficient": "2",
                "n0": "3",
                "labels": [{"side": "unbarred", "row": 0, "column": 0, "value": "7"}],
            }],
        },
        "pair_cell_styles": {
            "0:unbarred:0:0": {
                "fill": "#ff0000",
                "stroke": "#0000ff",
                "line_style": "dashed",
            },
        },
    }
    source = r"2\pair + f(x)"
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": source}],
        "embedded_pair_ids": ["line:pair:0"],
        "embedded_pairs": [pair],
    })

    assert r"2_{3}" in result
    assert r"\mathord" not in result
    assert "{HTML}{FF0000}" in result
    assert "dashed" in result
    assert "7" in result
    assert r"\pair" not in result
    assert r"\begin{ydpair}" in result
    assert r"\covar{" in result
    assert r"\convar{" in result
    assert r"\hpad{" not in result
    assert "dashed,draw=" not in result
    assert "f(x)" in result


def test_projector_export_uses_endpoint_colour_and_direction_arrow() -> None:
    graph = {
        "geometry": {
            "first_layer_x": 1,
            "layer_step": 2,
            "left_boundary": 0,
            "right_boundary": 5,
            "step": 1,
            "node_width": 1,
            "operator_padding": 0.45,
            "level_spacing": 1,
            "top_margin": 1,
            "line_color": "#111111",
            "line_width": 2,
            "operator_line_width": 3,
            "symmetriser_color": "#eeeeee",
            "antisymmetriser_color": "#333333",
        },
        "nodes": [{
            "index": 0,
            "layer": 0,
            "kind": "symmetriser",
            "labels": [1],
            "input_labels": [1],
            "output_labels": [1],
        }],
        "connections": [],
        "external_inputs": [{"boundary_label": 1, "port": {"node": 0, "label": 1}}],
        "external_outputs": [{"boundary_label": 1, "port": {"node": 0, "label": 1}}],
        "boundary_labels": [1],
        "free_levels": {"0": {"1": 0}},
        "in_direction": "left",
        "out_direction": "right",
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"x": 1, "y": 1}},
            "port_orders": {},
            "boundary_orders": {"input": [1], "output": [1]},
            "free_levels": graph["free_levels"],
            "line_colors": {"right-anchor:0->input:0:1": "#ff0000"},
            "mode": "evaluate",
        }],
    })

    assert "{HTML}{FF0000}" in result
    assert "draw=btcolor" in result
    assert r"\begin{projector}" in result
    assert r"\startnodes" in result
    assert r"\layer{\symmetriser[][draw=btcolor0]{1}}" in result
    assert r"\endnodes" in result
    assert "{>,draw=btcolor0}" in result
    assert r"\tikzset" not in result
    assert "bt/export-line" not in result
    assert "rectangle" not in result
    assert "operator_width=" not in result
    assert "line_width=" not in result
    assert "line width=" not in result


def test_projector_export_inserts_level_permutation_between_layers() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [
            {"index": 0, "layer": 0, "kind": "symmetriser", "labels": [1]},
            {"index": 1, "layer": 1, "kind": "antisymmetriser", "labels": [1]},
        ],
        "connections": [{
            "source": {"node": 1, "label": 1},
            "target": {"node": 0, "label": 1},
            "boundary_label": 1,
        }],
        "external_inputs": [],
        "external_outputs": [],
        "boundary_labels": [1, 2, 3],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"y": 0}, "1": {"y": 1}},
            "port_orders": {
                "0": {"input": [1], "output": [1]},
                "1": {"input": [1], "output": [1]},
            },
            "free_levels": {
                "0": {"2": 1, "3": 2},
                "1": {"2": 0, "3": 2},
            },
            "mode": "create",
        }],
    })

    assert r"\layer{\permute{1,2,3}{2,1,3}}" in result


def test_projector_export_preserves_coloured_boundary_permutations() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [{
            "index": 0, "layer": 0, "kind": "symmetriser",
            "labels": [2, 1], "input_labels": [2, 1],
            "output_labels": [2, 1],
        }],
        "connections": [],
        "external_inputs": [
            {"boundary_label": label, "port": {"node": 0, "label": label}}
            for label in (1, 2)
        ],
        "external_outputs": [
            {"boundary_label": label, "port": {"node": 0, "label": label}}
            for label in (1, 2)
        ],
        "boundary_labels": [1, 2],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"y": 0.5}},
            "port_orders": {"0": {"input": [2, 1], "output": [2, 1]}},
            "boundary_orders": {"input": [1, 2], "output": [1, 2]},
            "line_colors": {"right-anchor:0->input:0:1": "#9141ac"},
            "mode": "create",
        }],
    })

    assert result.count(r"\permute{1,2}{2,1}") == 1
    assert result.count(r"\permute[,draw=btcolor0]{1,2}{2,1}") == 1
    assert "{HTML}{9141AC}" in result


def test_projector_export_derives_each_boundary_permutation_from_its_own_wiring() -> None:
    order = (10, 20, 30)
    identity = (1, 2, 3)

    def command(targets: tuple[int, ...]) -> str:
        values = ",".join(map(str, targets))
        return rf"\layer{{\permute{{1,2,3}}{{{values}}}}}"

    for input_ports in permutations(order):
        for output_ports in permutations(order):
            graph = {
                "geometry": {"top_margin": 0, "level_spacing": 1},
                "nodes": [{
                    "index": 0, "layer": 0, "kind": "symmetriser",
                    "labels": list(order),
                }],
                "connections": [],
                "external_inputs": [
                    {"boundary_label": level + 1,
                     "port": {"node": 0, "label": label}}
                    for level, label in enumerate(input_ports)
                ],
                "external_outputs": [
                    {"boundary_label": level + 1,
                     "port": {"node": 0, "label": label}}
                    for level, label in enumerate(output_ports)
                ],
                "boundary_labels": [1, 2, 3],
                "display": {"operator_columns": [], "strands": []},
            }
            result = whiteboard_latex({
                "blocks": [{"id": "line", "source": r"\birdtracks"}],
                "embedded_projector_ids": ["line:projector:0"],
                "embedded_projectors": [{
                    "graph": graph,
                    "positions": {"0": {"y": 1}},
                    "port_orders": {
                        "0": {"input": list(order), "output": list(order)},
                    },
                    "boundary_orders": {
                        "input": [1, 2, 3], "output": [1, 2, 3],
                    },
                    "mode": "create",
                }],
            })
            layers = [
                line.strip() for line in result.splitlines()
                if line.strip().startswith(r"\layer")
            ]
            left_targets = tuple(order.index(label) + 1 for label in output_ports)
            right_targets = tuple(input_ports.index(label) + 1 for label in order)
            expected = [] if left_targets == identity else [command(left_targets)]
            expected.append(r"\layer{\symmetriser{3}}")
            if right_targets != identity:
                expected.append(command(right_targets))
            assert layers == expected


def test_projector_export_carries_colour_through_explicit_permutation() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [{
            "index": 0, "layer": 0, "kind": "permutation",
            "labels": [1, 2], "mapping": [[1, 2], [2, 1]],
        }],
        "connections": [],
        "external_inputs": [
            {"boundary_label": 1, "port": {"node": 0, "label": 1}},
            {"boundary_label": 2, "port": {"node": 0, "label": 2}},
        ],
        "external_outputs": [
            {"boundary_label": 1, "port": {"node": 0, "label": 2}},
            {"boundary_label": 2, "port": {"node": 0, "label": 1}},
        ],
        "boundary_labels": [1, 2],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"y": 0.5}},
            "port_orders": {
                "0": {"input": [1, 2], "output": [1, 2]},
            },
            "boundary_orders": {"input": [1, 2], "output": [1, 2]},
            "line_colors": {"right-anchor:0->input:0:1": "#ff0000"},
            "mode": "create",
        }],
    })

    assert r"\layer{\permute[draw=btcolor0,]{1,2}{2,1}}" in result


def test_projector_export_inserts_identity_permutation_between_sa_layers() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [
            {"index": 0, "layer": 0, "kind": "symmetriser", "labels": [1]},
            {"index": 1, "layer": 1, "kind": "antisymmetriser", "labels": [1]},
        ],
        "connections": [{
            "source": {"node": 1, "label": 1},
            "target": {"node": 0, "label": 1},
            "boundary_label": 1,
        }],
        "external_inputs": [],
        "external_outputs": [],
        "boundary_labels": [1, 2, 3],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"y": 0}, "1": {"y": 0}},
            "port_orders": {
                "0": {"input": [1], "output": [1]},
                "1": {"input": [1], "output": [1]},
            },
            "free_levels": {
                "0": {"2": 1, "3": 2},
                "1": {"2": 1, "3": 2},
            },
            "mode": "create",
        }],
    })

    assert r"\layer{\permute{1,2,3}{1,2,3}}" in result


def test_projector_export_keeps_boundary_labels_and_colours_on_their_faces() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [
            {"index": 0, "layer": 0, "kind": "symmetriser", "labels": [1, 3]},
            {"index": 1, "layer": 1, "kind": "antisymmetriser", "labels": [3, 2]},
            {"index": 2, "layer": 2, "kind": "symmetriser", "labels": [1, 3]},
        ],
        "connections": [
            {"source": {"node": 2, "label": 1},
             "target": {"node": 0, "label": 1}},
            {"source": {"node": 2, "label": 3},
             "target": {"node": 1, "label": 3}},
            {"source": {"node": 1, "label": 3},
             "target": {"node": 0, "label": 3}},
        ],
        "external_inputs": [
            {"boundary_label": 1, "port": {"node": 2, "label": 1}},
            {"boundary_label": 3, "port": {"node": 2, "label": 3}},
            {"boundary_label": 2, "port": {"node": 1, "label": 2}},
        ],
        "external_outputs": [
            {"boundary_label": 1, "port": {"node": 0, "label": 1}},
            {"boundary_label": 2, "port": {"node": 0, "label": 3}},
            {"boundary_label": 3, "port": {"node": 1, "label": 2}},
        ],
        "boundary_labels": [1, 2, 3],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {
                "0": {"y": 0.5}, "1": {"y": 1.5}, "2": {"y": 0.5},
            },
            "port_orders": {
                "0": {"input": [1, 3], "output": [1, 3]},
                "1": {"input": [3, 2], "output": [3, 2]},
                "2": {"input": [1, 3], "output": [1, 3]},
            },
            "boundary_orders": {"input": [1, 2, 3], "output": [1, 2, 3]},
            "free_levels": {
                "0": {"2": 2}, "1": {"1": 0}, "2": {"2": 2},
            },
            "line_colors": {"right-anchor:1->input:1:2": "#9141ac"},
            "mode": "create",
        }],
    })

    layers = [
        line.strip() for line in result.splitlines()
        if line.strip().startswith(r"\layer")
    ]
    assert layers == [
        r"\layer{\symmetriser{2}\freelines{1}}",
        r"\layer{\permute{1,2,3}{1,2,3}}",
        r"\layer{\freelines{1}\antisymmetriser[,][,draw=btcolor0]{2}}",
        r"\layer{\permute[,,draw=btcolor0]{1,2,3}{1,2,3}}",
        r"\layer{\symmetriser{2}\freelines[draw=btcolor0]{1}}",
        r"\layer{\permute[,,draw=btcolor0]{1,2,3}{1,3,2}}",
    ]


def test_compiled_export_orders_repacked_disjoint_operators_vertically() -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Antisymmetriser((3, 4)),
        PermutationNode(Permutation.identity(), support=(2,)),
        PermutationNode(Permutation.from_cycle(2, 3), support=(2, 3, 4)),
        Antisymmetriser((3, 4)),
        PermutationNode(Permutation.identity(), support=(2,)),
        Symmetriser((1, 2)),
    ])
    graph = widget_graph(projector)
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": default_positions(projector),
            "port_orders": {
                str(node["index"]): {
                    "input": node["input_labels"],
                    "output": node["output_labels"],
                }
                for node in graph["nodes"]
            },
            "boundary_orders": {"input": [1, 2, 3, 4], "output": [1, 2, 3, 4]},
            "free_levels": graph["free_levels"],
            "mode": "evaluate",
        }],
    })

    assert graph["display"]["operator_columns"] == [[0, 1], [4, 6]]
    assert result.count(r"\layer{\symmetriser{2}\antisymmetriser{2}}") == 2
    assert r"\freelines{2}\antisymmetriser{2}\symmetriser{2}" not in result


def _export_projector_widget(widget) -> str:
    return whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [widget],
    })


def test_moved_three_layer_export_uses_repaired_display_routes() -> None:
    from copy import deepcopy
    from birdtracks.projectors.widget import projector_widget

    value = Projector([Symmetriser((1, 2)), Symmetriser((3, 4)),
                       Antisymmetriser((2, 3)), Antisymmetriser((3, 5))])
    widget = projector_widget(value, mode="evaluate")
    session = widget._editor_session
    session.move({session.state.node_ids[3]: {**widget.positions["3"], "y": 5}},
                 base_revision=session.state.revision, geometry=widget.graph["geometry"])
    widget._publish_editor()
    before = deepcopy(widget.editor_state)
    result = _export_projector_widget(widget)
    layers = [line.strip() for line in result.splitlines() if line.strip().startswith(r"\layer")]
    assert layers == [
        r"\layer{\symmetriser{2}\symmetriser{2}\freelines{1}}",
        r"\layer{\permute{1,2,3,4,5}{1,2,3,4,5}}",
        r"\layer{\freelines{1}\antisymmetriser{2}\freelines{2}}",
        r"\layer{\permute{1,2,3,4,5}{1,2,4,3,5}}",
        r"\layer{\freelines{3}\antisymmetriser{2}}",
        r"\layer{\permute{1,2,3,4,5}{1,2,4,3,5}}",
    ]
    assert widget.editor_state == before
    assert widget.projector == value


def test_compiled_connector_exports_visible_strand_colour_through_hidden_permutation() -> None:
    from birdtracks.projectors.widget import projector_widget

    value = Projector([Symmetriser((1, 2)),
                       PermutationNode(Permutation.from_cycle(1, 2)), Symmetriser((1, 2))])
    widget = projector_widget(value, mode="evaluate")
    widget.line_colors = {"output:2:1->input:0:2": "#9141ac"}
    result = _export_projector_widget(widget)
    assert "{HTML}{9141AC}" in result
    assert r"\layer{\symmetriser[,][,draw=btcolor0]{2}}" in result
    assert r"\layer{\permute[,draw=btcolor0]{1,2}{2,1}}" in result
    assert r"\layer{\symmetriser[draw=btcolor0,][,]{2}}" in result


def test_compiled_coloured_boundary_permutations_match_start_and_end_nodes() -> None:
    from birdtracks.projectors.widget import projector_widget

    swap = PermutationNode(Permutation.from_cycle(1, 2))
    widget = projector_widget(Projector([swap, Symmetriser((1, 2)), swap]), mode="evaluate")
    widget.line_colors = {"output:1:2->left-anchor:0": "#9141ac",
                          "right-anchor:0->input:1:2": "#9141ac"}
    result = _export_projector_widget(widget)
    assert r"\startnodes[draw=btcolor0,]" in result
    assert r"\endnodes[draw=btcolor0,]" in result
    assert r"\layer{\permute[draw=btcolor0,]{1,2}{2,1}}" in result
    assert r"\layer{\symmetriser[,draw=btcolor0]{2}}" in result
    assert r"\layer{\permute[,draw=btcolor0]{1,2}{2,1}}" in result


def test_single_operator_export_omits_identity_connectors() -> None:
    from birdtracks.projectors.widget import projector_widget

    result = _export_projector_widget(projector_widget(Projector([Symmetriser((1, 2))])))
    assert r"\layer{\symmetriser{2}}" in result
    assert r"\permute" not in result


def test_compiled_identity_connector_preserves_coloured_pass_through_and_boundary() -> None:
    from birdtracks.projectors.widget import projector_widget

    widget = projector_widget(Projector([Symmetriser((1, 2)), Antisymmetriser((2, 3))]),
                              mode="evaluate")
    # Strand 1 passes through the second column, sharing its visible colour
    # with the right boundary and the operator's input face.
    widget.line_colors = {"right-anchor:0->input:0:1": "#9141ac"}
    result = _export_projector_widget(widget)
    assert r"\layer{\symmetriser[,][draw=btcolor0,]{2}\freelines{1}}" in result
    assert r"\layer{\permute[draw=btcolor0,,]{1,2,3}{1,2,3}}" in result
    assert r"\layer{\freelines[draw=btcolor0]{1}\antisymmetriser{2}}" in result
    assert r"\endnodes[draw=btcolor0,,]" in result


def test_free_line_label_collision_does_not_hide_layer_permutation() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [
            {"index": 0, "layer": 0, "kind": "symmetriser", "labels": [1, 2]},
            {"index": 1, "layer": 1, "kind": "symmetriser", "labels": [1, 2]},
        ],
        "connections": [{
            "source": {"node": 1, "label": 1},
            "target": {"node": 0, "label": 1},
            "boundary_label": 1,
        }],
        "external_inputs": [],
        "external_outputs": [],
        "boundary_labels": [1, 2, 3],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"y": 0.5}, "1": {"y": 0.5}},
            "port_orders": {
                "0": {"input": [1, 2], "output": [1, 2]},
                "1": {"input": [1, 2], "output": [1, 2]},
            },
            # Boundary strand 2 shares a number with a local operator port.
            "free_levels": {"0": {"2": 2}, "1": {"3": 2}},
            "mode": "create",
        }],
    })

    assert r"\layer{\permute{1,2,3}{1,2,3}}" in result


def test_projector_colour_follows_connection_across_multiple_layers() -> None:
    graph = {
        "geometry": {"top_margin": 0, "level_spacing": 1},
        "nodes": [
            {"index": 0, "layer": 0, "kind": "symmetriser", "labels": [1]},
            {"index": 1, "layer": 1, "kind": "antisymmetriser", "labels": [2]},
            {"index": 2, "layer": 2, "kind": "symmetriser", "labels": [1]},
        ],
        "connections": [{
            "source": {"node": 2, "label": 1},
            "target": {"node": 0, "label": 1},
        }],
        "external_inputs": [],
        "external_outputs": [],
        "boundary_labels": [1, 2],
        "display": {"operator_columns": [], "strands": []},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"\birdtracks"}],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {
                "0": {"y": 0}, "1": {"y": 1}, "2": {"y": 0},
            },
            "port_orders": {},
            "free_levels": {
                "0": {"2": 1}, "1": {"1": 0}, "2": {"2": 1},
            },
            "line_colors": {"output:2:1->input:0:1": "#ff0000"},
            "mode": "create",
        }],
    })

    assert r"\symmetriser[][draw=btcolor0]{1}" in result
    assert r"\freelines[draw=btcolor0]{1}\antisymmetriser{1}" in result
    assert r"\symmetriser[draw=btcolor0][]{1}" in result


def test_calculated_svg_is_exported_and_uses_saved_cell_style() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
        'viewBox="0 0 20 20"><g data-cell="cell-1">'
        '<rect x="1" y="1" width="8" height="8" fill="white" '
        'stroke="currentColor"/><text x="5" y="6">4</text></g></svg>'
    )
    result = whiteboard_latex({
        "blocks": [{
            "id": "calculation-1",
            "source": "= ",
            "calculation_svg": svg,
            "calculation_cell_styles": {"cell-1": {"fill": "#00ff00"}},
        }],
    })

    assert "{HTML}{00FF00}" in result
    assert "rectangle" in result
    assert "4" in result


def test_export_replaces_definition_command_with_equals() -> None:
    result = whiteboard_latex({
        "blocks": [{"id": "definition", "source": r"P_1 \def \birdtracks"}],
    })

    assert result == r"P_1 = \birdtracks"
    assert r"\def" not in result


def test_export_can_include_equation_line_alignment() -> None:
    result = whiteboard_latex({
        "blocks": [
            {"id": "first", "source": r"A = \birdtracks"},
            {"id": "second", "source": r"B \def C"},
        ],
    }, include_equation_alignment=True)

    assert result == "A =& \\birdtracks \\\\\nB =& C"


def test_pair_export_options_omit_colours_and_pad_to_n0_rows() -> None:
    pair = {
        "pair_expression": {"terms": [{
            "barred": [1],
            "unbarred": [2, 1],
            "coefficient": "1",
            "n0": "5",
            "labels": [],
        }]},
        "pair_cell_styles": {"0:unbarred:0:0": {"fill": "#ff0000"}},
    }
    result = whiteboard_latex({
        "blocks": [{"id": "pair", "source": r"\pair"}],
        "embedded_pair_ids": ["pair:pair:0"],
        "embedded_pairs": [pair],
    }, include_colors=False, pad_to_n0=True)

    assert r"\hpad{2}" in result
    assert r"\definecolor" not in result
    assert "FF0000" not in result
    assert "fill=" not in result


def test_calculated_pair_exports_as_ydpair_with_splitbox() -> None:
    result = whiteboard_latex({
        "blocks": [{
            "id": "calculation",
            "source": "= ",
            "calculation_svg": "<svg/>",
            "pair_expression_tree": {
                "kind": "pair",
                "term": {
                    "kind": "pair", "barred": [], "unbarred": [1],
                    "coefficient": r"\frac{2}{3}", "n0": "1",
                },
                "drawing": {"cells": [{
                    "row": 0, "column": 0,
                    "labels": [
                        {"text": "1", "barred": True},
                        {"text": "1", "barred": False},
                    ],
                }]},
            },
            "calculation_cell_styles": {"0:0": {"fill": "#ff0000"}},
        }],
    })

    assert r"\begin{ydpair}" in result
    assert r"\splitbox{\overline{1}}{1}" in result
    assert r"\frac{2}{3}" in result
    assert r"\tikz[" not in result
    assert "{HTML}{FF0000}" in result
    assert "fill=btcolor0" in result


def test_calculated_pair_exports_antiboxes_and_drawing_only_cells() -> None:
    result = whiteboard_latex({
        "blocks": [{
            "id": "calculation",
            "source": "= ",
            "calculation_svg": "<svg/>",
            "pair_expression_tree": {
                "kind": "sum",
                "children": [{
                    "kind": "pair",
                    "term": {
                        "barred": [1], "unbarred": [1],
                        "coefficient": "1", "n0": "2",
                    },
                    "drawing": {"cells": [{
                        "row": 1, "column": 0, "dashed": False,
                        "bullet": False,
                        "labels": [{"text": "1", "barred": True}],
                    }]},
                }, {
                    "kind": "pair",
                    "term": {
                        "barred": [1], "unbarred": [],
                        "coefficient": "1", "n0": "1",
                    },
                }, {
                    "kind": "pair",
                    "term": {
                        "barred": [], "unbarred": [],
                        "coefficient": "1", "n0": "1",
                    },
                    "drawing": {"cells": [{
                        "row": 0, "column": 0, "dashed": True,
                        "bullet": False,
                        "labels": [{"text": "1", "barred": True}],
                    }]},
                }]},
        }],
    })

    assert result.count(r"\overline{1}") == 2
    assert r"\overline{\overline{1}}" not in result
    assert r"[] \ensuremath{\bullet}" in result
    assert r"[dashed] \ensuremath{\overline{1}}" in result
    assert result.count(r"\oplus") == 2
    assert r"\mathbin" not in result


def test_calculated_pair_uses_authoritative_drawing_cells_and_coordinates() -> None:
    document = {
        "blocks": [{
            "id": "calculation",
            "source": "= ",
            "calculation_svg": "<svg/>",
            "pair_expression_tree": {
                "kind": "pair",
                "term": {
                    "barred": [2], "unbarred": [],
                    "coefficient": "3", "n0": "3",
                },
                "drawing": {"cells": [
                    {"row": 0, "column": 2, "dashed": True,
                     "bullet": False,
                     "labels": [{"text": "1", "barred": True}]},
                    {"row": 2, "column": 0, "dashed": False,
                     "bullet": False,
                     "labels": [{"text": "1", "barred": True}]},
                    {"row": 2, "column": 1, "dashed": False,
                     "bullet": True, "labels": []},
                ]},
            },
            "calculation_cell_styles": {"0:0": {"fill": "#f8e45c"}},
        }],
    }
    result = whiteboard_latex(document)

    assert r"[fill=btcolor0,dashed] \ensuremath{\overline{1}}" in result
    assert r"\hpad{" not in result
    assert (
        r"[] \ensuremath{\overline{1}} & [] \ensuremath{\bullet}"
        in result
    )
    assert result.count(r"\ensuremath{\overline{1}}") == 2
    assert result.count(r"\ensuremath{\bullet}") == 1

    padded_result = whiteboard_latex(document, pad_to_n0=True)
    assert r"\hpad{1}" in padded_result


@pytest.mark.parametrize("operator", [r"\oplus", r"\otimes"])
def test_unspaced_pair_prefactor_is_exported_once(operator: str) -> None:
    result = whiteboard_latex({
        "blocks": [{"id": "line", "source": rf"\pair{operator}2_3\pair"}],
        "embedded_pair_ids": ["line:pair:0", "line:pair:1"],
        "embedded_pairs": [
            {"pair_expression": {"terms": [{
                "barred": [], "unbarred": [1], "coefficient": "1", "n0": "1",
            }]}},
            {"pair_expression": {"terms": [{
                "barred": [1], "unbarred": [1], "coefficient": "2", "n0": "3",
            }]}},
        ],
    })

    assert rf"{operator}2_3" not in result
    assert result.count(r"2_{3}") == 1
    assert r"\mathord" not in result


def test_new_syntax_export_compiles(tmp_path: Path) -> None:
    pdflatex = shutil.which("pdflatex")
    if pdflatex is None:
        pytest.skip("pdflatex is not installed")
    pair = {
        "pair_expression": {"terms": [{
            "barred": [1], "unbarred": [2], "coefficient": "1", "n0": "0",
            "labels": [{"side": "unbarred", "row": 0, "column": 0, "value": "i"}],
        }]},
    }
    graph = {
        "geometry": {"node_width": 2, "level_spacing": 1.1},
        "nodes": [{
            "index": 0, "layer": 0, "kind": "antisymmetriser",
            "labels": [1, 2], "input_labels": [1, 2], "output_labels": [1, 2],
        }],
        "connections": [],
        "external_inputs": [
            {"boundary_label": label, "port": {"node": 0, "label": label}}
            for label in (1, 2)
        ],
        "external_outputs": [
            {"boundary_label": label, "port": {"node": 0, "label": label}}
            for label in (1, 2)
        ],
        "boundary_labels": [1, 2],
        "display": {"operator_columns": [], "strands": []},
    }
    source = whiteboard_latex({
        "blocks": [{"id": "line", "source": r"$\pair\quad\birdtracks$"}],
        "embedded_pair_ids": ["line:pair:0"],
        "embedded_pairs": [pair],
        "embedded_projector_ids": ["line:projector:0"],
        "embedded_projectors": [{
            "graph": graph,
            "positions": {"0": {"x": 1, "y": 0}},
            "boundary_orders": {"input": [1, 2], "output": [1, 2]},
            "mode": "evaluate",
        }],
    }, include_preamble=True)
    from birdtracks.projectors.widget import projector_widget

    swap = PermutationNode(Permutation.from_cycle(1, 2))
    compiled = projector_widget(Projector([swap, Symmetriser((1, 2)),
                                          swap, Symmetriser((1, 2))]), mode="evaluate")
    compiled.line_colors = {"output:1:2->left-anchor:0": "#9141ac",
                            "output:3:2->input:1:1": "#9141ac",
                            "right-anchor:0->input:3:1": "#9141ac"}
    source = source.replace(r"\end{document}",
                            "\n$" + _export_projector_widget(compiled) + "$\n" + r"\end{document}")
    source = source.replace(
        r"\end{document}",
        "\n" + r"\birdtracksetup{box_size=2.4em}"
        "\n" + r"\makeatletter"
        r"\ifdim\bt@boxwidth=2.4em\else\PackageError{test}{box_size did not set box width}{}\fi"
        r"\ifdim\bt@boxheight=2.4em\else\PackageError{test}{box_size did not set box height}{}\fi"
        r"\ifdim\bt@ydboxsize=2.4em\else\PackageError{test}{box_size did not set ydpair size}{}\fi"
        r"\makeatother"
        "\n" + r"\newbox\btsizetest"
        r"\setbox\btsizetest=\hbox{$\begin{ydpair}\covar{[]}\end{ydpair}$}"
        r"\ifdim\wd\btsizetest<2.39em\PackageError{test}{box_size was not rendered}{}\fi"
        "\n" + r"$\begin{ydpair}[box_size=1.7em]\covar{[] \splitbox{\bar 1}{1}}\end{ydpair}$"
        "\n" + r"$\begin{projector}[operator_width=2em]\layer{\symmetriser[draw=red][draw=blue]{2}}\end{projector}$"
        "\n" + r"$\begin{tracedprojector}[trace_gap=2em]"
        r"\leftconnect{\permute[<,{<,draw=red}]{1,2}{2,1}}" "\n\n"
        r"\topprojector[line_spacing=.8em]{\begin{projector}\layer{\symmetriser{2}}\end{projector}}"
        "\n\n"
        r"\bottomprojector[line_spacing=1.2em]{\begin{projector}\layer{\antisymmetriser{2}}\end{projector}}"
        "\n\n"
        r"\rightconnect{\permute[>,]{1,2}{1,2}}"
        r"\end{tracedprojector}$"
        "\n" + r"\end{document}",
    )
    tex_file = tmp_path / "export.tex"
    tex_file.write_text(source, encoding="utf-8")
    environment = os.environ.copy()
    environment["TEXINPUTS"] = str(Path("latex").resolve()) + os.pathsep
    completed = subprocess.run(
        [pdflatex, "-halt-on-error", "-interaction=nonstopmode", tex_file.name],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
