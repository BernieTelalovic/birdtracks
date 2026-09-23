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

    assert r"\mathord{2_{3}}" in result
    assert "{HTML}{FF0000}" in result
    assert "dashed" in result
    assert "7" in result
    assert r"\pair" not in result
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
    assert "--" in result
    assert "rectangle" in result


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
