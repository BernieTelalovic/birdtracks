"""Unit tests for projector display state kept outside algebraic values."""

from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import re

import pytest

from birdtracks import (
    Antisymmetriser,
    Connection,
    NodePort,
    Permutation,
    PermutationNode,
    Projector,
    ProjectorSum,
    Symmetriser,
)
from birdtracks.projectors.layout import (
    default_positions,
    validated_positions,
    widget_graph,
)
from birdtracks.projectors.style import load_projector_style


def example_projector() -> Projector:
    return Projector(
        [
            Antisymmetriser({1, 4}),
            Symmetriser({2, 4}),
            Antisymmetriser({1, 3}),
            Antisymmetriser({2, 3}),
        ]
    )


def save_editor(editor: object) -> None:
    """Simulate the frontend's atomic Save permutation payload."""
    revision = editor.save_request + 1  # type: ignore[attr-defined]
    editor.save_request = revision  # type: ignore[attr-defined]
    editor.save_snapshot = {  # type: ignore[attr-defined]
        "revision": revision,
        "positions": editor.positions,  # type: ignore[attr-defined]
        "port_orders": editor.port_orders,  # type: ignore[attr-defined]
        "free_levels": editor.free_levels,  # type: ignore[attr-defined]
        "boundary_orders": editor.boundary_orders,  # type: ignore[attr-defined]
        "effective_coefficient": editor.effective_coefficient,  # type: ignore[attr-defined]
    }


def test_default_positions_follow_layers_without_changing_projector() -> None:
    projector = example_projector()
    original_hash = hash(projector)
    positions = default_positions(projector)
    geometry = widget_graph(projector)["geometry"]

    assert positions["0"]["x"] == geometry["first_layer_x"]
    assert positions["1"]["x"] == geometry["first_layer_x"] + geometry["layer_step"]
    assert positions["2"]["x"] == positions["1"]["x"]
    assert positions["3"]["x"] == geometry["first_layer_x"] + 2 * geometry["layer_step"]
    for index, position in positions.items():
        line_count = max(1, len(projector.nodes[int(index)].support))
        start = (
            (position["y"] - geometry["top_line_level"])
            / geometry["level_spacing"]
            - (line_count - 1) / 2
        )
        assert start == pytest.approx(round(start))
    assert hash(projector) == original_hash


def test_default_operator_rectangles_do_not_overlap_within_a_layer() -> None:
    projector = example_projector()
    positions = default_positions(projector)
    geometry = widget_graph(projector)["geometry"]

    for layer in projector.layers:
        bounds = []
        for index in layer:
            line_count = len(projector.nodes[index].support)
            half_height = (
                (line_count - 1) * geometry["level_spacing"]
                + 2 * geometry["operator_padding"]
            ) / 2
            centre = positions[str(index)]["y"]
            bounds.append((centre - half_height, centre + half_height))
        bounds.sort()
        assert all(
            upper < next_lower
            for (_lower, upper), (next_lower, _next_upper) in zip(
                bounds, bounds[1:]
            )
        )


def test_widget_graph_serializes_node_kinds_and_topology() -> None:
    graph = widget_graph(example_projector())

    assert graph["coefficient"] == {"numerator": "1", "denominator": "1"}
    assert graph["base_coefficient"] == {
        "numerator": "1",
        "denominator": "1",
    }
    assert graph["port_swap_sign"] == 1
    assert graph["layer_count"] == 3
    assert graph["geometry"]["operator_width"] == 1.0
    assert graph["geometry"]["operator_padding"] == (
        graph["geometry"]["level_spacing"]
        * graph["geometry"]["operator_padding_fraction"]
    )
    assert graph["geometry"]["coefficient_font_size"] == pytest.approx(
        0.75 * graph["geometry"]["level_spacing"]
    )
    assert graph["geometry"]["fraction_font_size"] == pytest.approx(
        0.75 * graph["geometry"]["level_spacing"]
    )
    assert graph["geometry"]["fraction_line_width"] == graph["geometry"]["line_width"]
    assert graph["geometry"]["layer_step"] == 1 + graph["geometry"]["step"]
    assert (
        graph["geometry"]["first_layer_x"]
        - graph["geometry"]["operator_width"] / 2
        - graph["geometry"]["left_boundary"]
    ) == pytest.approx(graph["geometry"]["step"] / 2)
    assert graph["display"]["corridor_widths"][0] >= graph["geometry"]["step"]
    assert graph["display"]["corridor_widths"][-1] >= graph["geometry"]["step"]
    assert [node["kind"] for node in graph["nodes"]] == [  # type: ignore[index]
        "antisymmetriser",
        "symmetriser",
        "antisymmetriser",
        "antisymmetriser",
    ]
    assert graph["nodes"][1]["input_labels"] == [2, 4]  # type: ignore[index]
    assert graph["nodes"][1]["output_labels"] == [2, 4]  # type: ignore[index]
    assert graph["connections"] == [
        {
            "source": {"node": 1, "label": 4},
            "target": {"node": 0, "label": 4},
            "boundary_label": 4,
        },
        {
            "source": {"node": 2, "label": 1},
            "target": {"node": 0, "label": 1},
            "boundary_label": 1,
        },
        {
            "source": {"node": 3, "label": 2},
            "target": {"node": 1, "label": 2},
            "boundary_label": 2,
        },
        {
            "source": {"node": 3, "label": 3},
            "target": {"node": 2, "label": 3},
            "boundary_label": 3,
        },
    ]
    assert graph["boundary_labels"] == [1, 2, 3, 4]
    assert graph["free_levels"] == {
        "0": {"2": 2, "3": 3},
        "1": {},
        "2": {"1": 0, "4": 3},
    }
    assert graph["external_inputs"] == [
        {"boundary_label": 4, "port": {"node": 1, "label": 4}},
        {"boundary_label": 1, "port": {"node": 2, "label": 1}},
        {"boundary_label": 2, "port": {"node": 3, "label": 2}},
        {"boundary_label": 3, "port": {"node": 3, "label": 3}},
    ]
    assert graph["external_outputs"] == [
        {"boundary_label": 1, "port": {"node": 0, "label": 1}},
        {"boundary_label": 4, "port": {"node": 0, "label": 4}},
        {"boundary_label": 2, "port": {"node": 1, "label": 2}},
        {"boundary_label": 3, "port": {"node": 2, "label": 3}},
    ]


def test_custom_positions_only_override_vertical_level() -> None:
    projector = example_projector()
    default_x = default_positions(projector)["2"]["x"]

    assert validated_positions(projector, {2: (12, 34)})["2"] == {
        "x": default_x,
        "y": 34.0,
    }


def test_connection_permutation_keeps_the_same_boundary_label_at_both_ends() -> None:
    projector = Projector(
        [Symmetriser({1}), Antisymmetriser({4})],
        connections=[Connection(NodePort(1, 4), NodePort(0, 1))],
    )

    graph = widget_graph(projector)

    assert graph["external_inputs"] == [
        {"boundary_label": 4, "port": {"node": 1, "label": 4}}
    ]
    assert graph["external_outputs"] == [
        {"boundary_label": 4, "port": {"node": 0, "label": 1}}
    ]
    assert graph["boundary_labels"] == [4]


def test_exact_projector_coefficient_is_serialized_for_display() -> None:
    projector = -example_projector() / 3

    assert projector.coefficient == Fraction(-1, 3)
    assert widget_graph(projector)["coefficient"] == {
        "numerator": "-1",
        "denominator": "3",
    }


def test_crossing_reducing_odd_antisymmetriser_swap_changes_display_sign() -> None:
    projector = Projector(
        [
            Antisymmetriser({1, 2}),
            Symmetriser({10}),
            Symmetriser({20}),
        ],
        connections=[
            Connection(NodePort(1, 10), NodePort(0, 2)),
            Connection(NodePort(2, 20), NodePort(0, 1)),
        ],
        coefficient=Fraction(2, 3),
    )

    graph = widget_graph(projector)

    assert graph["nodes"][0]["input_labels"] == [2, 1]  # type: ignore[index]
    assert graph["nodes"][0]["output_labels"] == [1, 2]  # type: ignore[index]
    assert graph["port_swap_sign"] == -1
    assert graph["coefficient"] == {"numerator": "-2", "denominator": "3"}
    assert graph["base_coefficient"] == graph["coefficient"]


def test_crossing_reducing_symmetriser_swap_does_not_change_sign() -> None:
    projector = Projector(
        [Symmetriser({1, 2}), Symmetriser({10}), Symmetriser({20})],
        connections=[
            Connection(NodePort(1, 10), NodePort(0, 2)),
            Connection(NodePort(2, 20), NodePort(0, 1)),
        ],
    )

    graph = widget_graph(projector)

    assert graph["nodes"][0]["input_labels"] == [2, 1]  # type: ignore[index]
    assert graph["port_swap_sign"] == 1
    assert graph["coefficient"] == {"numerator": "1", "denominator": "1"}


def test_detangle_preserves_topology_with_an_intermediate_permutation() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2)),
            Symmetriser((1, 2)),
        ],
        port_orders={
            index: {"input": (1, 2), "output": (1, 2)}
            for index in range(3)
        },
    )

    detangled = projector.detangle()

    assert detangled == projector
    assert detangled.collapse() == projector.collapse()
    assert detangled.nodes == projector.nodes
    assert detangled.connections == projector.connections
    assert detangled.input_boundary == projector.input_boundary
    assert detangled.output_boundary == projector.output_boundary
    assert detangled.detangle().port_orders == detangled.port_orders


def test_permutation_strands_keep_distinct_input_and_output_route_labels() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2)),
            PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2)),
            Symmetriser((1, 2)),
        ]
    )

    graph = widget_graph(projector)

    assert [connection["boundary_label"] for connection in graph["connections"]] == [
        2,
        1,
        1,
        2,
    ]


def test_invalid_custom_positions_are_rejected() -> None:
    projector = example_projector()
    with pytest.raises(ValueError, match="unknown node"):
        validated_positions(projector, {8: (1, 2)})
    with pytest.raises(TypeError, match="coordinates"):
        validated_positions(projector, {0: (True, 2)})


def test_yaml_style_changes_relative_geometry(tmp_path: Path) -> None:
    default_path = Path(__file__).parents[2] / "src/birdtracks/projectors/projector-widget.yaml"
    custom_path = tmp_path / "projector-style.yaml"
    custom = re.sub(
        r"^level_spacing:.*$",
        "level_spacing: 0.6",
        default_path.read_text(),
        flags=re.MULTILINE,
    )
    custom = re.sub(r"^step:.*$", "step: 1.25", custom, flags=re.MULTILINE)
    custom_path.write_text(custom)

    style = load_projector_style(custom_path)
    graph = widget_graph(example_projector(), style)

    assert graph["geometry"]["level_spacing"] == 0.6
    assert graph["geometry"]["layer_step"] == 2.25
    assert (
        graph["geometry"]["first_layer_x"]
        - graph["geometry"]["operator_width"] / 2
        - graph["geometry"]["left_boundary"]
    ) == pytest.approx(0.625)


def test_optional_widget_contains_synchronised_graph_and_positions() -> None:
    pytest.importorskip("anywidget")
    projector = example_projector()
    default_x = default_positions(projector)["0"]["x"]

    evaluation = projector.evaluate({0: (15, 25)})
    widget = evaluation._term_editors[0]  # type: ignore[attr-defined]

    assert widget.mode == "evaluate"  # type: ignore[attr-defined]
    assert widget.graph == {  # type: ignore[attr-defined]
        **widget_graph(projector),
        "term_sign": "",
        "term_leading": True,
    }
    assert widget.positions["0"] == {  # type: ignore[attr-defined]
        "x": default_x,
        "y": 25.0,
    }
    assert widget.port_orders["0"] == {  # type: ignore[attr-defined]
        "input": [1, 4],
        "output": [1, 4],
    }
    assert widget.free_levels == widget_graph(projector)["free_levels"]  # type: ignore[attr-defined]
    assert widget.boundary_orders == {  # type: ignore[attr-defined]
        "input": [1, 2, 3, 4],
        "output": [1, 2, 3, 4],
    }
    assert widget.effective_coefficient == {  # type: ignore[attr-defined]
        "numerator": "1",
        "denominator": "1",
    }
    data, _metadata = widget._repr_mimebundle_()
    assert "application/vnd.jupyter.widget-view+json" in data


def test_projector_create_opens_a_blank_creator() -> None:
    pytest.importorskip("anywidget")

    creation = Projector.create()
    editor = creation._term_editors[0]  # type: ignore[attr-defined]

    assert creation.mode == "create"  # type: ignore[attr-defined]
    assert creation._toolbar.mode == "create"  # type: ignore[attr-defined]
    assert editor.mode == "create"  # type: ignore[attr-defined]
    assert editor.active_line is True  # type: ignore[attr-defined]
    assert editor.graph["creator"] is True  # type: ignore[attr-defined]
    assert editor.graph["nodes"] == []  # type: ignore[attr-defined]
    assert editor.graph["connections"] == []  # type: ignore[attr-defined]
    assert editor.projector == Projector([])  # type: ignore[attr-defined]
    assert editor.projector_sum == ProjectorSum((Projector([]),))  # type: ignore[attr-defined]
    assert creation.projector_sum == ProjectorSum((Projector([]),))  # type: ignore[attr-defined]
    assert creation.projector == Projector([])  # type: ignore[attr-defined]
    assert editor.layout.width == "100%"  # type: ignore[attr-defined]
    assert editor.layout.flex == "0 0 auto"  # type: ignore[attr-defined]


def test_creator_canvas_does_not_depend_on_toolbar_local_helpers() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    creator_source = source.split("function renderCreator", 1)[1].split(
        "function renderConfigured", 1
    )[0]

    assert "const save = document.createElement(\"button\")" in creator_source
    assert "const save = button(" not in creator_source


def test_canvas_vertical_bounds_follow_visible_levels_and_mode() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert "const top = contentTop - spacing / 3;" in source
    assert "const bottom = contentBottom + spacing / 3;" in source
    assert "yFor(node.level) - geometry.operator_padding" in source
    assert 'if (interactionMode === "create") {' in source
    assert 'canvasViewport.style.height = `${viewportHeight}rem`' in source


def test_canvas_drag_targets_are_deliberately_generous() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert "lineDragActive ? 3.25 : 1.4" in source
    assert "geometry.handle_radius * 2.25" in source
    assert "Math.abs(displacement) < 0.2" in source
    assert "Math.min(nodeWidth, spacing) * 0.08" in source
    assert "Math.min(nodeWidth, spacing) * 0.28" in source
    assert "Math.min(nodeWidth, spacing) * 0.38" in source
    assert "Math.min(nodeWidth, spacing) * 0.2" in source
    assert 'class: "birdtracks-line-control-hit"' in source
    assert 'class: "birdtracks-add-line-control-hit"' in source
    assert 'if (interactionMode !== "create") return;' in source
    assert 'const blocked = event.target.closest?.(' in source


def test_creator_fraction_multiplier_has_keyboard_and_exact_controls() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'button("Multiply by a fraction"' in source
    assert 'event.key !== "Enter"' in source
    assert 'aria-label", "Multiplier numerator"' in source
    assert 'aria-label", "Multiplier denominator"' in source
    assert 'action === "multiply"' in source
    assert "event.detail.editorId === editorId" in source
    assert "let top = multiplierTop" in source
    assert "let bottom = multiplierBottom" in source
    assert 'localMultiply.textContent = "·"' in source
    assert 'controlDown && interactionMode === "create"' in source
    assert 'workspace.classList.toggle("fraction-open", open)' in source
    assert "setLocalFractionOpen(localFraction.hidden)" in source
    css = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.css"
    ).read_text()
    assert ".birdtracks-creator-workspace.fraction-open" in css
    fraction_input = css.split(".birdtracks-local-fraction input {", 1)[1].split(
        "}", 1
    )[0]
    assert "border: 0" in fraction_input
    assert "background: transparent" in fraction_input
    assert "font-family: serif" in fraction_input
    assert 'input === localNumerator && event.key === "/"' in source
    assert "localDenominator.focus()" in source
    assert "localDenominator.select()" in source
    css = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.css"
    ).read_text()
    local_fraction = css.split(".birdtracks-local-fraction {", 1)[1].split(
        "}", 1
    )[0]
    assert "width: 4.5rem" in local_fraction
    assert "border-radius: 0.55rem" in local_fraction
    assert "box-shadow:" in local_fraction


def test_canvas_free_lines_reorder_both_directions_and_persist_levels() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert (
        "return movingUp ? insertionProbe <= centre : insertionProbe < centre;"
        in source
    )
    assert "const requestedCentre = requestedLevel + (moving.width - 1) / 2" in source
    assert "Math.ceil(relative - 0.5)" in source
    assert "Math.floor(relative + 0.5)" in source
    assert "function normalizeCreatorLayers()" in source
    assert "assignLayerLevels(layer, layerUnits(layer));" in source
    assert "const connectionStrandLabel = new Map();" in source
    assert "free_levels: savedFreeLevels" in source
    assert 'model.set("free_levels", savedFreeLevels);' in source


def test_default_free_levels_never_overlap_an_operator_block() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2, 3)),
            PermutationNode(Permutation.from_cycle(1, 3), support=(1, 3)),
            Antisymmetriser((2, 3)),
        ]
    )
    graph = widget_graph(projector)
    positions = default_positions(projector)
    geometry = graph["geometry"]

    for layer_index, layer in enumerate(projector.layers):
        occupied = set()
        for node_index in layer:
            width = len(projector.nodes[node_index].support)
            centre = positions[str(node_index)]["y"]
            start = round(
                (centre - geometry["top_line_level"])
                / geometry["level_spacing"]
                - (width - 1) / 2
            )
            occupied.update(range(start, start + width))
        assert occupied.isdisjoint(
            graph["free_levels"][str(layer_index)].values()
        )


def test_configured_canvas_repacks_saved_free_lines_before_drawing() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    normalization = source.split("function normalizeConfiguredLayers()", 1)[1].split(
        "normalizeConfiguredLayers();", 1
    )[0]
    assert 'kind: "node"' in normalization
    assert 'kind: "free"' in normalization
    assert "cursor += unit.width" in normalization


def test_canvas_packs_sign_space_without_overlap_and_compacts_empty_layers() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert "const left = 0" in source
    assert "const right = usesCompiledDisplay()" in source
    assert 'svg.setAttribute("viewBox", `${box.left} ${box.top}' in source
    assert "function compactEmptyLayers()" in source
    assert "occupied.map((layer, index) => [layer, index])" in source
    assert ".filter(([layer]) => compactedLayer.has(Number(layer)))" in source
    assert "function collapseFreeLineLayers()" in source
    assert '.filter((node) => node.kind === "permutation")' in source
    assert 'incoming.source.type === "right-anchor"' in source


def test_evaluate_mode_accepts_an_exact_node_expansion_request() -> None:
    pytest.importorskip("anywidget")
    projector = Projector([Symmetriser((1, 2, 3))])
    evaluation = projector.evaluate()
    editor = evaluation._term_editors[0]  # type: ignore[attr-defined]

    assert evaluation._toolbar.mode == "evaluate"  # type: ignore[attr-defined]
    editor.mode = "create"  # type: ignore[attr-defined]
    editor.expand_node_request = {"node": 0, "revision": 1}  # type: ignore[attr-defined]
    assert len(evaluation._history) == 1  # type: ignore[attr-defined]

    editor.mode = "evaluate"  # type: ignore[attr-defined]
    editor.expand_node_request = {"node": 0, "revision": 2}  # type: ignore[attr-defined]

    assert len(evaluation._history) == 2  # type: ignore[attr-defined]
    assert editor.active_line is False  # type: ignore[attr-defined]
    assert all(
        current.active_line is True
        for current in evaluation._term_editors  # type: ignore[attr-defined]
    )
    assert evaluation._history[-1].collapse() == projector.collapse()  # type: ignore[attr-defined]
    assert len(evaluation.children) == 4  # type: ignore[attr-defined]
    assert "birdtracks-equation-equals" in evaluation.children[2].children[0].value  # type: ignore[attr-defined]
    assert '<line x1="4" y1="9"' in evaluation.children[2].children[0].value  # type: ignore[attr-defined]

    active = evaluation._term_editors[0]  # type: ignore[attr-defined]
    active.zoom = 0.5
    equals = evaluation.children[2].children[0]  # type: ignore[attr-defined]
    assert equals.layout.width == "0.75rem"
    assert equals.layout.height == "0.75rem"

    editor.expand_node_request = {"node": 0, "revision": 3}  # type: ignore[attr-defined]
    assert len(evaluation._history) == 2  # type: ignore[attr-defined]

    active = evaluation._term_editors[0]  # type: ignore[attr-defined]
    active.undo_request += 1  # type: ignore[attr-defined]
    assert len(evaluation._history) == 1  # type: ignore[attr-defined]
    assert len(evaluation.children) == 3  # type: ignore[attr-defined]
    assert editor.active_line is True  # type: ignore[attr-defined]


def test_global_undo_on_first_equation_line_delegates_to_local_editor() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Symmetriser((1, 2))]).evaluate()
    editor = evaluation._term_editors[0]  # type: ignore[attr-defined]

    editor.undo_request += 1

    assert len(evaluation._history) == 1  # type: ignore[attr-defined]
    assert editor.local_undo_command == 1


def test_global_undo_uses_equation_history_even_when_historical_editor_selected() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Symmetriser((1, 2, 3))]).evaluate()
    historical = evaluation._term_editors[0]  # type: ignore[attr-defined]
    historical.expand_node_request = {"node": 0, "revision": 1}
    assert len(evaluation._history) == 2  # type: ignore[attr-defined]

    historical.undo_request += 1

    assert len(evaluation._history) == 1  # type: ignore[attr-defined]
    assert evaluation._term_editors == (historical,)  # type: ignore[attr-defined]


def test_one_toolbar_undo_removes_exactly_one_of_three_equation_lines() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Symmetriser((1, 2, 3, 4))]).evaluate(
        detangler=False
    )
    for revision in (1, 2):
        editor = next(
            item
            for item in evaluation._term_editors  # type: ignore[attr-defined]
            if any(node["kind"] == "symmetriser" for node in item.graph["nodes"])
        )
        node_index = next(
            node["index"]
            for node in editor.graph["nodes"]
            if node["kind"] == "symmetriser"
        )
        editor.expand_node_request = {
            "node": node_index,
            "recursive_edge": "top",
            "revision": revision,
        }
    assert len(evaluation._line_states) == 3  # type: ignore[attr-defined]

    evaluation._toolbar.undo_request = {  # type: ignore[attr-defined]
        "editor_id": evaluation._term_editors[0].model_id,  # type: ignore[attr-defined]
        "revision": 1,
    }

    assert len(evaluation._line_states) == 2  # type: ignore[attr-defined]
    assert len(evaluation._rows) == 2  # type: ignore[attr-defined]


def test_canvas_has_ctrl_revealed_local_controls_separate_from_global_undo() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'localUndo.className = "birdtracks-local-undo"' in source
    assert "workspace.append(canvasViewport, localUndo, localMultiply, localFraction)" in source
    assert "localUndo.appendChild(undoIcon())" in source
    assert "Math.min(...operatorXs) + Math.max(...operatorXs)" in source
    assert "point.matrixTransform(matrix)" in source
    assert "screenPoint.x - workspaceBox.left" in source
    assert 'model.on("change:local_undo_command", localUndoFromPython)' in source
    assert (
        'localUndo.classList.toggle("visible", controlDown && interactionMode === "evaluate")'
        in source
    )
    assert 'window.addEventListener("blur", clearModifier)' in source
    toolbar_undo = source.split("function undoButton()", 1)[1].split(
        "const addSymmetriser", 1
    )[0]
    assert "undoEditorOperation()" not in toolbar_undo
    assert 'model.set("undo_request"' in toolbar_undo
    css = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.css"
    ).read_text()
    assert "left: 50%" in css
    assert "top: 50%" in css
    assert ".birdtracks-local-undo.visible" in css
    assert ".birdtracks-undo-icon circle" in css
    assert "stroke: white" in css
    local_icon_rule = css.split(
        ".birdtracks-local-undo .birdtracks-undo-icon", 1
    )[1].split("}", 1)[0]
    assert "background: transparent" in local_icon_rule
    assert "border: 0" in local_icon_rule


def test_active_line_changes_redraw_recursive_controls() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'model.on("change:active_line", redrawActiveLine)' in source
    assert 'model.off("change:active_line", redrawActiveLine)' in source


def test_toolbar_modes_and_trace_have_high_contrast_pressed_state() -> None:
    root = Path(__file__).parents[2] / "src/birdtracks/projectors/static"
    source = (root / "projector-widget.js").read_text()
    css = (root / "projector-widget.css").read_text()

    assert 'createTab.setAttribute("aria-pressed"' in source
    assert 'evaluateTab.setAttribute("aria-pressed"' in source
    selected = css.split(".birdtracks-icon-button.selected {", 1)[1].split("}", 1)[0]
    assert "background: #303640" in selected
    assert "color: #f9fafb" in selected
    assert "inset 0 4px 7px" in selected
    assert "transform: translateY(2px)" in selected
    selected_icon = css.split(
        ".birdtracks-icon-button.selected svg,", 1
    )[1].split("}", 1)[0]
    assert "stroke: #f9fafb" in selected_icon


@pytest.mark.parametrize(
    ("edge", "remaining_support"),
    [("top", frozenset((2, 3))), ("bottom", frozenset((1, 2)))],
)
def test_calculator_edge_controls_apply_selected_recursive_expansion(
    edge: str, remaining_support: frozenset[int]
) -> None:
    pytest.importorskip("anywidget")
    projector = Projector([Antisymmetriser((1, 2, 3))])
    evaluation = projector.evaluate()

    evaluation._term_editors[0].expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "recursive_edge": edge,
        "revision": 1,
    }

    expanded = evaluation._history[-1]  # type: ignore[attr-defined]
    assert expanded.collapse() == projector.collapse()
    assert any(
        isinstance(node, Antisymmetriser)
        and node.support == remaining_support
        for term, _coefficient in expanded
        for node in term.nodes
    )


def test_calculator_draws_hoverable_tear_controls_without_removing_double_click() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'class: "birdtracks-recursion-control"' in source
    assert "centreX - radius * 1.35" in source
    assert "centreX + radius * 1.35" in source
    assert 'class: "birdtracks-recursion-control-hit"' in source
    assert "width: nodeWidth" in source
    assert 'control.classList.add("active")' in source
    assert "nodeLayer, handles, annotations, interactions" in source
    assert "interactions.append(hitTarget, control)" in source
    assert "saveProjector(node.index, edge)" in source
    assert "saveProjector(node.index);" in source
    css = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.css"
    ).read_text()
    assert "stroke-width: var(--birdtracks-operator-line-width)" in css
    assert (
        ".birdtracks-recursion-control-hit:hover "
        "+ .birdtracks-recursion-control"
    ) in css


def test_canvas_expansion_omits_terms_annihilated_through_a_permutation() -> None:
    pytest.importorskip("anywidget")
    projector = Projector(
        [
            Symmetriser((1, 2)),
            Symmetriser((1, 3)),
            Antisymmetriser((2, 3)),
        ]
    )
    evaluation = projector.evaluate()
    editor = evaluation._term_editors[0]  # type: ignore[attr-defined]

    editor.expand_node_request = {"node": 1, "revision": 1}  # type: ignore[attr-defined]

    assert len(evaluation._history[-1]) == 1  # type: ignore[attr-defined]
    assert len(evaluation._term_editors) == 1  # type: ignore[attr-defined]


def test_zero_evaluation_row_is_a_single_prefactor_sized_zero() -> None:
    pytest.importorskip("anywidget")
    evaluation = ProjectorSum(()).evaluate()

    zero_row = evaluation.children[1]
    assert len(zero_row.children) == 1
    assert 'class="birdtracks-zero"' in zero_row.children[0].value
    assert "birdtracks-equation-equals" not in zero_row.children[0].value


def test_trace_wraps_equation_but_evaluates_only_latest_line() -> None:
    pytest.importorskip("anywidget")
    projector = Projector([Symmetriser((1, 2))])
    evaluation = projector.evaluate(detangler=False)
    first_editor = evaluation._term_editors[0]  # type: ignore[attr-defined]
    first_editor.expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "revision": 1,
    }
    latest = evaluation.current_projector_sum

    evaluation._toolbar.trace_enabled = True  # type: ignore[attr-defined]
    assert evaluation._trace_polynomial == next(  # type: ignore[attr-defined]
        iter(latest.trace().collapse())
    )[1]
    assert len(evaluation._rows) == 2  # type: ignore[attr-defined]
    for row in evaluation._rows:  # type: ignore[attr-defined]
        assert sum(
            "birdtracks-trace-symbol" in getattr(child, "value", "")
            for child in row.children
        ) == 1
        assert all(
            r"\(" not in getattr(child, "value", "")
            for child in row.children
        )
        trace_open = next(
            child
            for child in row.children
            if "birdtracks-trace-open" in child._dom_classes
        )
        assert trace_open.layout.margin == "0 -1.55rem 0 0"
    assert evaluation._trace_result_row is evaluation.children[-2]  # type: ignore[attr-defined]
    polynomial_html = evaluation._trace_result_row.children[1].value  # type: ignore[attr-defined]
    assert "birdtracks-polynomial-fraction" in polynomial_html
    assert "N<sup>2</sup> + " in polynomial_html
    assert "\\frac" not in polynomial_html


def test_terms_can_be_reordered_inside_trace_brackets() -> None:
    pytest.importorskip("anywidget")
    positive = Projector([Symmetriser((1, 2))])
    negative = Projector([Antisymmetriser((1, 2))])
    evaluation = ProjectorSum(((positive, 1), (negative, -1))).evaluate(
        detangler=False
    )
    original_editors = evaluation._term_editors  # type: ignore[attr-defined]
    original_signs = evaluation._term_signs  # type: ignore[attr-defined]
    original_value = evaluation.current_projector_sum

    evaluation._toolbar.trace_enabled = True  # type: ignore[attr-defined]
    original_editors[0].term_order_request = {  # type: ignore[attr-defined]
        "target": 1,
        "revision": 1,
    }

    assert evaluation._term_editors == original_editors[::-1]  # type: ignore[attr-defined]
    assert evaluation._term_signs == original_signs[::-1]  # type: ignore[attr-defined]
    assert evaluation.current_projector_sum == original_value
    assert evaluation._term_editors[0].term_leading  # type: ignore[attr-defined]
    expected_leading_sign = "-" if original_signs[1] < 0 else ""
    expected_trailing_sign = "-" if original_signs[0] < 0 else "+"
    assert (  # type: ignore[attr-defined]
        evaluation._term_editors[0].term_sign == expected_leading_sign
    )
    assert (  # type: ignore[attr-defined]
        evaluation._term_editors[1].term_sign == expected_trailing_sign
    )
    assert not evaluation._term_editors[1].term_leading  # type: ignore[attr-defined]

    row = evaluation._rows[0]  # type: ignore[attr-defined]
    assert "birdtracks-trace-open" in row.children[0]._dom_classes
    assert row.children[1:3] == original_editors[::-1]
    assert "birdtracks-trace-close" in row.children[3]._dom_classes


def test_trace_toggle_off_restores_projector_only_equation() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Symmetriser((1, 2))]).evaluate(detangler=False)
    original_children = evaluation._rows[0].children  # type: ignore[attr-defined]

    evaluation._toolbar.trace_enabled = True  # type: ignore[attr-defined]
    evaluation._toolbar.trace_enabled = False  # type: ignore[attr-defined]

    assert evaluation._trace_polynomial is None  # type: ignore[attr-defined]
    assert evaluation._trace_result_row is None  # type: ignore[attr-defined]
    assert evaluation._rows[0].children == original_children  # type: ignore[attr-defined]
    assert evaluation.children == (  # type: ignore[attr-defined]
        evaluation._toolbar,
        *evaluation._rows,
        evaluation._save_step_button,
    )


def test_expansion_while_traced_adds_bracketed_second_last_line() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Symmetriser((1, 2))]).evaluate(detangler=False)
    evaluation._toolbar.trace_enabled = True  # type: ignore[attr-defined]
    polynomial = evaluation._trace_polynomial  # type: ignore[attr-defined]
    polynomial_row = evaluation._trace_result_row  # type: ignore[attr-defined]

    evaluation._term_editors[0].expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "revision": 1,
    }

    assert evaluation._trace_polynomial is polynomial  # type: ignore[attr-defined]
    assert evaluation.children[-2] is polynomial_row
    assert evaluation.children[-3] is evaluation._rows[-1]  # type: ignore[attr-defined]
    assert "birdtracks-traced-row" in evaluation._rows[-1]._dom_classes  # type: ignore[attr-defined]
    assert "birdtracks-trace-symbol" in evaluation._rows[-1].children[1].value  # type: ignore[attr-defined]


def test_switching_to_create_mode_turns_trace_off() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Symmetriser((1, 2))]).evaluate(detangler=False)
    evaluation._toolbar.trace_enabled = True  # type: ignore[attr-defined]

    evaluation._toolbar.mode = "create"  # type: ignore[attr-defined]

    assert not evaluation._toolbar.trace_enabled  # type: ignore[attr-defined]
    assert evaluation._trace_result_row is None  # type: ignore[attr-defined]
    assert all(  # type: ignore[attr-defined]
        "birdtracks-traced-row" not in row._dom_classes
        for row in evaluation._rows
    )


def test_creator_inserts_a_signed_term_left_of_the_selected_term() -> None:
    pytest.importorskip("anywidget")
    creator = Projector.create()
    selected = creator._term_editors[0]  # type: ignore[attr-defined]

    creator._toolbar.add_term_request = {  # type: ignore[attr-defined]
        "sign": -1,
        "editor_id": selected.model_id,
        "revision": 1,
    }
    save_editor(selected)

    assert len(creator._term_editors) == 2  # type: ignore[attr-defined]
    assert creator._term_editors[1] is selected  # type: ignore[attr-defined]
    assert creator._term_signs == (-1, 1)  # type: ignore[attr-defined]
    assert creator._term_editors[0].term_sign == "-"  # type: ignore[attr-defined]
    assert creator._term_editors[1].term_sign == "+"  # type: ignore[attr-defined]
    assert creator._term_editors[0].graph["creator"]  # type: ignore[attr-defined]
    assert creator._term_editors[0].graph["nodes"] == []  # type: ignore[attr-defined]
    assert creator._term_editors[0].graph["connections"] == []  # type: ignore[attr-defined]
    assert creator._term_editors[0].layout.min_width == "0"  # type: ignore[attr-defined]
    assert creator._term_editors[1].layout.min_width == "0"  # type: ignore[attr-defined]

    creator._term_editors[0].term_sign_flip_request += 1  # type: ignore[attr-defined]

    assert creator._term_signs == (1, 1)  # type: ignore[attr-defined]

    creator._toolbar.mode = "evaluate"  # type: ignore[attr-defined]
    assert creator.mode == "evaluate"  # type: ignore[attr-defined]
    create_editors = creator._term_editors  # type: ignore[attr-defined]
    for editor in create_editors:
        save_editor(editor)
    assert all(  # type: ignore[attr-defined]
        editor not in create_editors for editor in creator._term_editors
    )
    assert all(  # type: ignore[attr-defined]
        not editor.graph.get("creator", False) for editor in creator._term_editors
    )


def test_creator_deletes_term_and_keeps_a_blank_canvas() -> None:
    pytest.importorskip("anywidget")
    creator = Projector.create(detangler=False)
    original = creator._term_editors[0]  # type: ignore[attr-defined]
    creator._toolbar.add_term_request = {  # type: ignore[attr-defined]
        "sign": 1,
        "editor_id": original.model_id,
        "revision": 1,
    }
    save_editor(original)
    inserted = creator._term_editors[0]  # type: ignore[attr-defined]

    inserted.term_delete_request += 1

    assert creator._term_editors == (original,)  # type: ignore[attr-defined]
    assert creator._term_signs == (1,)  # type: ignore[attr-defined]
    assert original.term_leading  # type: ignore[attr-defined]
    assert original.term_sign == ""  # type: ignore[attr-defined]

    original.term_delete_request += 1  # type: ignore[attr-defined]

    replacement = creator._term_editors[0]  # type: ignore[attr-defined]
    assert replacement is not original
    assert replacement.graph["creator"]
    assert replacement.graph["nodes"] == []
    assert creator._term_signs == (1,)  # type: ignore[attr-defined]


def test_creator_prefactor_right_click_requests_term_deletion() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text(encoding="utf-8")

    assert 'class: "birdtracks-prefactor-delete-target"' in source
    assert 'model.get("term_delete_request") + 1' in source
    assert 'prefactorTarget.addEventListener("contextmenu"' in source


def test_missing_saved_port_order_uses_graph_order() -> None:
    from birdtracks.projectors.widget import _projector_from_state

    projector = Projector(
        [Antisymmetriser((1, 2)), Antisymmetriser((2, 3))]
    )
    graph = widget_graph(projector)
    port_orders = {
        str(node["index"]): {
            "input": list(node["input_labels"]),
            "output": list(node["output_labels"]),
        }
        for node in graph["nodes"]
    }
    del port_orders["1"]

    restored = _projector_from_state(
        graph,
        port_orders,
        {
            "input": list(graph["boundary_labels"]),
            "output": list(graph["boundary_labels"]),
        },
    )

    assert restored == projector


def test_canvas_callback_errors_are_quiet_by_default(monkeypatch) -> None:
    pytest.importorskip("anywidget")
    from birdtracks.projectors import widget

    canvas = Projector([Symmetriser((1, 2))]).evaluate(detangler=False)
    editor = canvas._term_editors[0]  # type: ignore[attr-defined]
    error = RuntimeError("render callback failed")
    monkeypatch.setattr(
        widget,
        "_projector_from_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    editor.term_sign_flip_request += 1

    assert canvas._last_error is error  # type: ignore[attr-defined]
    assert canvas._term_signs == (1,)  # type: ignore[attr-defined]


def test_canvas_debug_mode_reraises_callback_errors(monkeypatch) -> None:
    pytest.importorskip("anywidget")
    from birdtracks.projectors import widget

    canvas = Projector([Symmetriser((1, 2))]).evaluate(
        detangler=False, debug=True
    )
    editor = canvas._term_editors[0]  # type: ignore[attr-defined]
    monkeypatch.setattr(
        widget,
        "_projector_from_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("render callback failed")
        ),
    )

    with pytest.raises(RuntimeError, match="render callback failed"):
        editor.term_sign_flip_request += 1


def test_trace_of_two_free_identity_strands_is_n_squared() -> None:
    from birdtracks.projectors.widget import _trace_scalar_polynomial

    identity = Projector(
        [PermutationNode(Permutation.identity(), support=(1, 2))]
    )

    assert _trace_scalar_polynomial(ProjectorSum((identity,))).coefficients == {
        2: Fraction(1)
    }


def test_creator_materializes_free_boundary_lines_before_saving() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'connection.source.type !== "right-anchor"' in source
    assert 'kind: "permutation"' in source
    assert "const livePresentation = snapshotEditorState()" in source
    assert "nodes = livePresentation.nodes" in source
    assert "connections = livePresentation.connections" in source
    assert 'mapping: [[label, label]]' in source


def test_expansion_components_replace_the_selected_term_in_display_order() -> None:
    pytest.importorskip("anywidget")
    value = ProjectorSum(
        (
            Projector([Symmetriser((1, 2))]),
            Projector([Symmetriser((3, 4))]),
            Projector([Symmetriser((5, 6))]),
        )
    )
    evaluation = value.evaluate()
    before = tuple(
        editor._source_projector  # type: ignore[attr-defined]
        for editor in evaluation._term_editors  # type: ignore[attr-defined]
    )

    evaluation._term_editors[1].expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "revision": 1,
    }
    after = tuple(
        editor._source_projector  # type: ignore[attr-defined]
        for editor in evaluation._term_editors  # type: ignore[attr-defined]
    )

    assert len(after) == 4
    assert after[0] % before[0]
    assert after[-1] % before[-1]
    assert all(
        isinstance(term.nodes[0], PermutationNode) for term in after[1:3]
    )


def test_projector_sum_terms_overlap_unused_canvas_margin() -> None:
    pytest.importorskip("anywidget")
    evaluation = ProjectorSum(
        (
            Projector([Symmetriser((1, 2))]),
            Projector([Symmetriser((3, 4))]),
        )
    ).evaluate()

    assert evaluation._term_editors[0].layout.margin == "0"  # type: ignore[attr-defined]
    assert evaluation._term_editors[1].layout.margin == "0"  # type: ignore[attr-defined]

    first_width = float(evaluation._term_editors[0].layout.width[:-2])  # type: ignore[attr-defined]
    for editor in evaluation._term_editors:  # type: ignore[attr-defined]
        editor.zoom = 0.5
    assert float(evaluation._term_editors[0].layout.width[:-2]) == first_width / 2  # type: ignore[attr-defined]
    assert evaluation._term_editors[1].layout.margin == "0"  # type: ignore[attr-defined]


def test_projector_sum_uses_compact_natural_term_widths() -> None:
    source = Path(
        __file__
    ).parents[2] / "src/birdtracks/projectors/widget.py"

    assert "width = max(\n                    96.0," in source.read_text()


def test_pure_permutations_use_one_bounded_display_wiring_corridor() -> None:
    pytest.importorskip("anywidget")
    three_layers = ProjectorSum(
        (
            Projector(
                [
                    PermutationNode(Permutation.from_cycle(1, 2)),
                    PermutationNode(Permutation.from_cycle(2, 3)),
                    PermutationNode(Permutation.from_cycle(1, 3)),
                ]
            ),
            Projector([PermutationNode(Permutation.identity(), support=(1, 2, 3))]),
        )
    ).evaluate()

    widths = [
        float(editor.layout.width[:-2])
        for editor in three_layers._term_editors  # type: ignore[attr-defined]
    ]
    assert max(widths) - min(widths) <= 40.0
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    assert "function drawCompiledDisplayStrands(lines, handles)" in source
    assert 'displayGraph.pure_permutation' in source


def test_stale_permutation_display_plan_cannot_constrain_created_operator_layers() -> None:
    """A live S/A added to a permutation term must move the right boundary."""
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    predicate = source.split("function usesPurePermutationDisplay()", 1)[1].split(
        "function bounds()", 1
    )[0]
    bounds = source.split("function bounds()", 1)[1].split(
        "function coordinates(endpoint)", 1
    )[0]

    assert 'interactionMode === "evaluate"' in predicate
    assert 'nodes.every((node) => node.kind === "permutation")' in predicate
    assert "const rightBoundary = compiled" in bounds
    assert "Number.isFinite(geometry.right_boundary)" in bounds
    assert "geometry.first_layer_x + (layers - 1) * layerStep + geometry.step" in bounds


def test_evaluate_display_uses_only_sa_columns_for_horizontal_geometry() -> None:
    permutation = PermutationNode(
        Permutation.from_cycle(1, 2), support=(1, 2, 3)
    )
    with_permutation_layers = widget_graph(
        Projector(
            [
                Antisymmetriser((1, 2, 3)),
                permutation,
                Antisymmetriser((1, 2, 3)),
            ]
        )
    )
    without_permutation_layers = widget_graph(
        Projector(
            [Antisymmetriser((1, 2, 3)), Antisymmetriser((1, 2, 3))]
        )
    )

    assert with_permutation_layers["display"]["operator_columns"] == [[0], [2]]
    width_growth = (
        with_permutation_layers["geometry"]["right_boundary"]
        - without_permutation_layers["geometry"]["right_boundary"]
    )
    assert 0 < width_growth <= 0.2 * with_permutation_layers["geometry"]["step"]


def test_compiled_evaluate_renderer_aligns_sa_columns_and_hides_permutation_nodes() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert "function displayColumn(nodeIndex)" in source
    assert "function xForNode(node)" in source
    assert "const corridorWidths = displayGraph.corridor_widths || []" in source
    assert "x += nodeWidth + (corridorWidths[index] ?? geometry.step)" in source
    assert 'if (!compiledDisplay || node.kind !== "permutation")' in source
    level_count = source.split("function levelCount()", 1)[1].split(
        "function usesPurePermutationDisplay()", 1
    )[0]
    assert "if (usesCompiledDisplay())" in level_count
    assert '.filter((node) => node.kind !== "permutation")' in level_count


def test_compiled_free_strands_are_flat_across_each_bypassed_sa_column() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    drawing = source.split("function drawCompiledDisplayStrands(lines, handles)", 1)[1].split(
        "function redraw()", 1
    )[0]

    assert "String(strand.strand_label)" in drawing
    assert "displayGraph.operator_columns[column][0]" in drawing
    assert "{ x: x + nodeWidth / 2, y }" in drawing
    assert "{ x: x - nodeWidth / 2, y }" in drawing
    assert "d: routedPath(points)" in drawing
    assert "const requestedLevel = Math.round(" in drawing
    assert "const level = freeLevelAtColumn(column, requestedLevel)" in drawing
    assert "occupied.add(operator.level + offset)" in drawing


def test_compiled_free_strands_keep_their_evaluate_drag_handles() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    drawing = source.split("function drawCompiledDisplayStrands(lines, handles)", 1)[1].split(
        "function redraw()", 1
    )[0]

    assert "boundaryLabel: connection.boundary_label" in source
    assert "Number(connection.boundaryLabel) === Number(strand.strand_label)" in drawing
    assert "Object.hasOwn(connection.route || {}, String(node.layer))" in drawing
    assert "drawRouteHandle(handles, liveConnection, node.layer, {" in drawing
    assert "displayX: x" in drawing
    assert "display?.displayX ?? xForLayer(layer)" in source
    assert "function reorderDisplayColumn(" in source


def test_line_and_sa_drag_reordering_restore_origin_before_insertion() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'connection.route[String(layer)] = originLevel' in source
    assert "Number(routed.boundaryLabel) === Number(display.strandLabel)" in source
    assert "reorderCreatorLayer(layer, connection, snappedLevel)" in source
    assert "const requestedLevel = node.level" in source
    assert "node.level = origin.level" in source
    assert "reorderCreatorLayer(node.layer, node, requestedLevel)" in source
    assert 'column, "node", node.index, origin.level, requestedLevel' in source
    assert "requestedLevel + moving.width - 1" in source
    assert "const requestedY = positions[String(node.index)].y" in source
    assert "positions[String(node.index)] = origin" in source


def test_layer_reordering_groups_all_segments_of_each_logical_free_strand() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    layer_units = source.split("function layerUnits(layer)", 1)[1].split(
        "function assignLayerLevels", 1
    )[0]
    assignment = source.split("function assignLayerLevels", 1)[1].split(
        "function normalizeCreatorLayers", 1
    )[0]

    assert "const logicalLines = new Map()" in layer_units
    assert "`strand:${connection.boundaryLabel}`" in layer_units
    assert "existing.connections.push(connection)" in layer_units
    assert "for (const connection of unit.connections)" in assignment


def test_generated_equation_rows_pack_free_lines_around_visible_sa_columns() -> None:
    pytest.importorskip("anywidget")
    canvas = Projector([Antisymmetriser((1, 2, 3))]).evaluate(detangler=False)
    canvas._term_editors[0].expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "recursive_edge": "top",
        "revision": 1,
    }

    for editor in canvas._term_editors:  # type: ignore[attr-defined]
        graph = editor.graph
        spacing = graph["geometry"]["level_spacing"]
        top = graph["geometry"]["top_line_level"]
        for column in graph["display"]["operator_columns"]:
            exact_layer = str(graph["nodes"][column[0]]["layer"])
            occupied: set[int] = set()
            for node_index in column:
                node = graph["nodes"][node_index]
                centre = editor.positions[str(node_index)]["y"]
                start = round(
                    (centre - top) / spacing - (len(node["labels"]) - 1) / 2
                )
                occupied.update(range(start, start + len(node["labels"])))
            free = set(graph["free_levels"][exact_layer].values())
            assert occupied.isdisjoint(free)
            assert occupied | free == set(range(len(graph["boundary_labels"])))


def test_every_term_uses_one_fixed_screen_scale_for_geometry_and_type() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    redraw = source.split("function redraw()", 1)[1].split(
        "function drawAddLineControl", 1
    )[0]

    assert "viewportWidth = zoom * 2.5 * measuredWidth / spacing" in redraw
    assert "annotations.getBBox()" in redraw
    assert "viewportHeight = zoom * 2.5 * box.height / spacing" in redraw
    assert "canvasViewport.style.flex = `0 0 ${viewportWidth}rem`" in redraw


def test_adjacent_sum_terms_do_not_paint_over_preceding_endpoint() -> None:
    css = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.css"
    ).read_text()
    rule = css.split(
        ".birdtracks-projector-sum .birdtracks-projector-widget svg {", 1
    )[1].split("}", 1)[0]

    assert "background: transparent" in rule


def test_signed_prefactor_has_equal_clearance_on_both_sides() -> None:
    style = load_projector_style()
    assert style["coefficient_space"] == pytest.approx(1.8)

    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    coefficient = source.split("function drawExactCoefficient", 1)[1].split(
        "function renderToolbar", 1
    )[0]

    assert "const unitMagnitude = magnitude === 1n && denominator === 1n" in coefficient
    assert "fontSize * 0.375" in coefficient
    assert "const signX = unitMagnitude" in coefficient


def test_equation_terms_use_fixed_vertical_level_grid_margins() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    bounds = source.split("function bounds()", 1)[1].split(
        "function coordinates(endpoint)", 1
    )[0]

    assert "const contentTop = yFor(0) - geometry.operator_padding" in bounds
    assert "const contentBottom = yFor(levelCount() - 1)" in bounds
    assert "operatorTops" not in bounds
    assert "operatorBottoms" not in bounds


def test_guides_and_add_line_controls_share_the_live_right_boundary() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    redraw = source.split("function redraw()", 1)[1].split(
        "function drawAddLineControl", 1
    )[0]
    add_control = source.split("function drawAddLineControl", 1)[1].split(
        "function drawEndpoint", 1
    )[0]

    assert "x2: box.rightBoundary" in redraw
    assert ': box.rightBoundary' in add_control


def test_create_undo_preserves_the_live_interaction_mode() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    undo = source.split("function undoEditorOperation()", 1)[1].split(
        "for (const [name, value]", 1
    )[0]

    assert "const modeBeforeUndo = interactionMode" in undo
    assert "interactionMode = modeBeforeUndo" in undo
    assert 'model.set("mode", modeBeforeUndo)' in undo


def test_deleting_an_operator_cleans_and_normalizes_its_wiring() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    deletion = source.split("function deleteNode(index)", 1)[1].split(
        "function resizeNode", 1
    )[0]

    assert "cleanupAfterNodeDeletion()" in deletion
    assert "validPort(connection.source) && validPort(connection.target)" in deletion
    assert "normalizeCreatorLayers()" in deletion
    assert "connections.push({ source, target, route: {} })" in deletion


def test_svg_vertical_bounds_include_intermediate_permutation_route_levels() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()
    levels = source.split("function levelCount()", 1)[1].split(
        "function usesPurePermutationDisplay()", 1
    )[0]

    assert "Object.values(connection.route || {})" in levels
    assert "...routedLevels" in levels


def test_recursive_expansion_uses_normal_layer_spacing_like_full_expansion() -> None:
    pytest.importorskip("anywidget")
    evaluation = Projector([Antisymmetriser((1, 2, 3))]).evaluate()
    editor = evaluation._term_editors[0]  # type: ignore[attr-defined]

    editor.expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "recursive_edge": "top",
        "revision": 1,
    }

    sandwiched = evaluation._term_editors[0]  # type: ignore[attr-defined]
    geometry = sandwiched.graph["geometry"]
    assert geometry["layer_step"] == pytest.approx(2.0)
    assert float(sandwiched.layout.width[:-2]) < 300


def test_inactive_canvas_lines_keep_evaluate_style_interactions() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert 'const permittedMode = model.get("active_line") ? mode : "evaluate";' in source
    assert 'if (!model.get("active_line")) {' not in source
    assert 'model.get("active_line")\n            && interactionMode === "evaluate"' in source


def test_permutation_node_widget_state_preserves_internal_strand_mapping() -> None:
    permutation = Permutation.from_cycle(1, 3, 2)
    graph = widget_graph(Projector([PermutationNode(permutation)]))

    assert graph["nodes"] == [
        {
            "index": 0,
            "layer": 0,
            "kind": "permutation",
            "labels": [1, 2, 3],
            "input_labels": [1, 2, 3],
            "output_labels": [1, 2, 3],
            "mapping": [[1, 3], [2, 1], [3, 2]],
        }
    ]


@pytest.mark.parametrize("node", [Symmetriser((4,)), Antisymmetriser((4,))])
def test_widget_renders_single_line_sa_as_free_identity_wiring(node: object) -> None:
    graph = widget_graph(Projector([node]))

    assert graph["nodes"][0]["kind"] == "permutation"
    assert graph["nodes"][0]["mapping"] == [[4, 4]]


def test_creator_dissolves_two_line_operator_instead_of_making_singleton() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/birdtracks/projectors/static/projector-widget.js"
    ).read_text()

    assert "node.labels.length === 2" in source
    assert 'message.textContent = "One-line operator replaced by a free line."' in source


def test_permutation_node_survives_widget_save() -> None:
    pytest.importorskip("anywidget")
    source = Projector([PermutationNode(Permutation.from_cycle(1, 2))])
    editor = source.evaluate()._term_editors[0]  # type: ignore[attr-defined]

    save_editor(editor)

    assert editor.projector == source  # type: ignore[attr-defined]


def test_creator_snapshot_builds_explicit_projector_topology() -> None:
    pytest.importorskip("anywidget")
    creation = Projector.create()
    editor = creation._term_editors[0]  # type: ignore[attr-defined]
    graph = {
        **editor.graph,  # type: ignore[attr-defined]
        "creator": False,
        "nodes": [
            {
                "index": 0,
                "layer": 0,
                "kind": "symmetriser",
                "labels": [10, 11],
                "input_labels": [10, 11],
                "output_labels": [10, 11],
            }
        ],
        "connections": [],
        "external_inputs": [
            {"boundary_label": 1, "port": {"node": 0, "label": 10}},
            {"boundary_label": 2, "port": {"node": 0, "label": 11}},
        ],
        "external_outputs": [
            {"boundary_label": 1, "port": {"node": 0, "label": 10}},
            {"boundary_label": 2, "port": {"node": 0, "label": 11}},
        ],
        "boundary_labels": [1, 2],
    }
    editor.save_snapshot = {  # type: ignore[attr-defined]
        "revision": 1,
        "graph": graph,
        "positions": {"0": {"x": 1.0, "y": 1.0}},
        "port_orders": {"0": {"input": [10, 11], "output": [10, 11]}},
        "free_levels": {},
        "boundary_orders": {"input": [1, 2], "output": [1, 2]},
        "effective_coefficient": {"numerator": "1", "denominator": "1"},
    }

    expected = Projector(
        [Symmetriser({10, 11})],
        input_boundary={1: NodePort(0, 10), 2: NodePort(0, 11)},
        output_boundary={1: NodePort(0, 10), 2: NodePort(0, 11)},
        port_orders={0: {"input": (10, 11), "output": (10, 11)}},
    )
    assert editor.projector == expected  # type: ignore[attr-defined]


def test_configurator_saves_boundary_permutations_and_relative_sign() -> None:
    pytest.importorskip("anywidget")
    source = example_projector()
    editor = source.evaluate()._term_editors[0]  # type: ignore[attr-defined]
    input_ports = dict(source.input_boundary)
    output_ports = dict(source.output_boundary)

    editor.boundary_orders = {  # type: ignore[attr-defined]
        "input": [2, 1, 3, 4],
        "output": [1, 2, 4, 3],
    }
    orders = dict(editor.port_orders)  # type: ignore[attr-defined]
    orders["0"] = dict(orders["0"])
    orders["0"]["input"] = list(reversed(orders["0"]["input"]))
    editor.port_orders = orders  # type: ignore[attr-defined]
    save_editor(editor)

    saved = editor.projector  # type: ignore[attr-defined]
    assert saved.coefficient == -source.coefficient
    assert saved.port_orders[0] == {
        "input": tuple(orders["0"]["input"]),
        "output": tuple(orders["0"]["output"]),
    }
    assert saved.input_boundary == {
        1: input_ports[2],
        2: input_ports[1],
        3: input_ports[3],
        4: input_ports[4],
    }
    assert saved.output_boundary == {
        1: output_ports[1],
        2: output_ports[2],
        3: output_ports[4],
        4: output_ports[3],
    }


def test_configurator_no_op_save_preserves_displayed_port_state() -> None:
    pytest.importorskip("anywidget")
    source = example_projector()
    editor = source.evaluate()._term_editors[0]  # type: ignore[attr-defined]

    save_editor(editor)

    saved = editor.projector  # type: ignore[attr-defined]
    assert saved.coefficient == source.coefficient
    assert saved == source
    assert saved.connections == source.connections
    assert saved.port_orders == {
        int(index): {
            "input": tuple(orders["input"]),
            "output": tuple(orders["output"]),
        }
        for index, orders in editor.port_orders.items()  # type: ignore[attr-defined]
    }
    assert widget_graph(saved)["port_swap_sign"] == 1
    assert [
        (node["input_labels"], node["output_labels"])
        for node in widget_graph(saved)["nodes"]
    ] == [
        (orders["input"], orders["output"])
        for orders in editor.port_orders.values()  # type: ignore[attr-defined]
    ]


def test_internal_antisymmetriser_swap_is_equal_and_reopens_exactly() -> None:
    pytest.importorskip("anywidget")
    source = example_projector()
    editor = source.evaluate()._term_editors[0]  # type: ignore[attr-defined]
    orders = {
        index: {side: list(order) for side, order in sides.items()}
        for index, sides in editor.port_orders.items()  # type: ignore[attr-defined]
    }
    orders["0"]["input"].reverse()
    editor.port_orders = orders  # type: ignore[attr-defined]
    editor.effective_coefficient = {  # type: ignore[attr-defined]
        "numerator": "-1",
        "denominator": "1",
    }
    save_editor(editor)

    saved = editor.projector  # type: ignore[attr-defined]
    reopened = editor.configuration.evaluate()._term_editors[0]  # type: ignore[attr-defined]

    assert saved == source
    assert reopened.port_orders == orders  # type: ignore[attr-defined]
    assert reopened.positions == editor.positions  # type: ignore[attr-defined]
    assert reopened.free_levels == editor.free_levels  # type: ignore[attr-defined]
    assert reopened.boundary_orders == editor.boundary_orders  # type: ignore[attr-defined]
    assert reopened.effective_coefficient == editor.effective_coefficient  # type: ignore[attr-defined]


def test_saved_configuration_replays_all_visual_state() -> None:
    pytest.importorskip("anywidget")
    source = example_projector()
    editor = source.evaluate()._term_editors[0]  # type: ignore[attr-defined]
    editor.positions = {  # type: ignore[attr-defined]
        **editor.positions,  # type: ignore[attr-defined]
        "0": {"x": editor.positions["0"]["x"], "y": 3.0},  # type: ignore[attr-defined]
    }
    editor.free_levels = {  # type: ignore[attr-defined]
        **editor.free_levels,  # type: ignore[attr-defined]
        "0": {"2": 3, "3": 2},
    }
    editor.boundary_orders = {  # type: ignore[attr-defined]
        "input": [2, 1, 3, 4],
        "output": [1, 2, 4, 3],
    }
    save_editor(editor)

    configuration = editor.configuration  # type: ignore[attr-defined]
    reopened = configuration.evaluate()._term_editors[0]  # type: ignore[attr-defined]

    assert reopened.projector == editor.projector  # type: ignore[attr-defined]
    assert reopened.positions == editor.positions  # type: ignore[attr-defined]
    assert reopened.port_orders == editor.port_orders  # type: ignore[attr-defined]
    assert reopened.free_levels == editor.free_levels  # type: ignore[attr-defined]
    assert reopened.boundary_orders == editor.boundary_orders  # type: ignore[attr-defined]
    assert reopened.effective_coefficient == editor.effective_coefficient  # type: ignore[attr-defined]

    copied_state = configuration.state()
    copied_state["positions"] = {}
    assert configuration.state()["positions"] == editor.positions  # type: ignore[attr-defined]


def test_saved_configuration_rebuilds_stale_display_routing() -> None:
    pytest.importorskip("anywidget")
    from birdtracks import ProjectorConfiguration

    source = example_projector()
    editor = source.evaluate(detangler=False)._term_editors[0]  # type: ignore[attr-defined]
    state = editor.configuration.state()  # type: ignore[attr-defined]
    state["graph"]["display"] = {
        "operator_columns": [[0]],
        "strands": [
            {
                "source": {
                    "kind": "operator_output",
                    "node": 0,
                    "label": 999,
                },
                "target": {"kind": "left_boundary", "label": 1},
                "strand_label": 1,
                "permutation_nodes": [],
            }
        ],
        "corridor_complexities": [],
        "crossing_count": 0,
        "pure_permutation": False,
    }
    configuration = ProjectorConfiguration.from_state(source, state)

    reopened = configuration.evaluate(detangler=False)._term_editors[0]  # type: ignore[attr-defined]

    assert reopened.graph["display"] == widget_graph(source)["display"]  # type: ignore[attr-defined]


def test_explicit_canvas_session_creates_and_resumes(tmp_path: Path) -> None:
    pytest.importorskip("anywidget")
    from birdtracks import ProjectorCanvasSession

    session_path = tmp_path / "calculation.canvas.json"
    created = Projector.create(session=session_path)

    assert session_path.exists()
    assert isinstance(created.session, ProjectorCanvasSession)  # type: ignore[attr-defined]
    assert created.session.path == session_path  # type: ignore[attr-defined]

    resumed = Projector.create(session=session_path)

    assert resumed.mode == "create"  # type: ignore[attr-defined]
    assert resumed.current_projector_sum == created.current_projector_sum  # type: ignore[attr-defined]
    assert len(resumed._line_states) == 1  # type: ignore[attr-defined]


def test_bare_canvas_session_name_uses_working_directory_expressions_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anywidget")
    monkeypatch.chdir(tmp_path)

    created = Projector.create(session="P1P2")
    expected = tmp_path / "expressions" / "P1P2.canvas.json"

    assert expected.exists()
    assert created.session.path == expected  # type: ignore[attr-defined]
    resumed = Projector.create(session="P1P2")
    assert resumed.current_projector_sum == created.current_projector_sum  # type: ignore[attr-defined]


def test_app_canvas_prompts_for_name_on_first_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anywidget")
    monkeypatch.chdir(tmp_path)
    from birdtracks.projectors.widget import projector_creator

    canvas = projector_creator(prompt_for_session=True, detangler=False)
    canvas._save_step_button.click()  # type: ignore[attr-defined]

    prompt = canvas._session_name_prompt  # type: ignore[attr-defined]
    assert prompt.layout.display == "flex"
    prompt.children[0].value = "P1P2"
    prompt.children[1].click()
    for editor in canvas._term_editors:  # type: ignore[attr-defined]
        editor.saved_revision = editor.save_command

    expected = tmp_path / "expressions" / "P1P2.canvas.json"
    assert expected.exists()
    assert canvas.session.path == expected  # type: ignore[attr-defined]
    assert prompt.layout.display == "none"


def test_relative_canvas_session_path_bypasses_expressions_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anywidget")
    monkeypatch.chdir(tmp_path)
    explicit = Path("sessions") / "P1P2"
    expected = Path("sessions") / "P1P2.canvas.json"

    created = Projector.create(session=explicit)

    assert expected.exists()
    assert created.session.path == expected  # type: ignore[attr-defined]
    assert not (tmp_path / "expressions").exists()


def test_app_kernel_uses_original_launch_directory_for_bare_session_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anywidget")
    launch_directory = tmp_path / "launch"
    kernel_directory = tmp_path / "package"
    launch_directory.mkdir()
    kernel_directory.mkdir()
    monkeypatch.chdir(kernel_directory)
    monkeypatch.setenv("BIRDTRACKS_EXPRESSION_ROOT", str(launch_directory))

    created = Projector.create(session="equation")

    expected = launch_directory / "expressions" / "equation.canvas.json"
    assert expected.exists()
    assert created.session.path == expected  # type: ignore[attr-defined]


def test_load_returns_single_latest_projector_by_bare_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anywidget")
    monkeypatch.chdir(tmp_path)
    source = Projector([Symmetriser((1, 2))])
    source.evaluate(session="saved-projector")

    from birdtracks import load

    loaded = load("saved-projector")

    assert loaded == source


def test_load_returns_multi_term_latest_projector_sum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("anywidget")
    monkeypatch.chdir(tmp_path)
    source = ProjectorSum(
        (
            Projector([Symmetriser((1, 2))]),
            Projector([Antisymmetriser((1, 2))]),
        )
    )
    source.evaluate(session="saved-sum")

    from birdtracks import load

    assert load("saved-sum") == source


def test_evaluation_canvas_session_preserves_term_state(tmp_path: Path) -> None:
    pytest.importorskip("anywidget")
    from birdtracks import ProjectorCanvasSession

    source = example_projector()
    expected_x = default_positions(source)["0"]["x"]
    session_path = tmp_path / "evaluation.canvas.json"
    canvas = source.evaluate({0: (17, 29)}, session=session_path)
    saved = ProjectorCanvasSession.load(session_path)
    state = saved.state()

    assert state["mode"] == "evaluate"
    assert state["lines"][0]["terms"][0]["state"]["positions"]["0"] == {
        "x": expected_x,
        "y": 29.0,
    }

    resumed = saved.open()

    assert resumed.current_projector_sum == canvas.current_projector_sum  # type: ignore[attr-defined]
    assert resumed._term_editors[0].positions["0"] == {  # type: ignore[attr-defined]
        "x": expected_x,
        "y": 29.0,
    }


def test_canvas_session_preserves_expansion_history(tmp_path: Path) -> None:
    pytest.importorskip("anywidget")

    source = Projector([Symmetriser((1, 2, 3))])
    session_path = tmp_path / "history.canvas.json"
    canvas = source.evaluate(session=session_path)
    first_editor = canvas._term_editors[0]  # type: ignore[attr-defined]
    first_editor.expand_node_request = {"node": 0, "revision": 1}

    resumed = Projector.create(session=session_path)

    assert resumed.mode == "evaluate"  # type: ignore[attr-defined]
    assert len(resumed._line_states) == 2  # type: ignore[attr-defined]
    assert resumed._history[-1].collapse() == source.collapse()  # type: ignore[attr-defined]
    assert all(
        not editor.active_line
        for editor in resumed._line_states[0][2]  # type: ignore[attr-defined]
    )
    assert all(
        editor.active_line
        for editor in resumed._line_states[-1][2]  # type: ignore[attr-defined]
    )


def test_canvas_session_collects_legacy_duplicate_term_panels(
    tmp_path: Path,
) -> None:
    pytest.importorskip("anywidget")
    from birdtracks import ProjectorCanvasSession
    from birdtracks.projectors.canvas_session import write_canvas_session

    projector = Projector([Symmetriser((1, 2))])
    session_path = tmp_path / "duplicates.canvas.json"
    projector.evaluate(session=session_path)
    document = ProjectorCanvasSession.load(session_path).state()
    original = document["lines"][0]["terms"][0]
    duplicates = []
    for numerator, denominator in ((1, 3), (1, 6)):
        duplicate = deepcopy(original)
        coefficient = {
            "numerator": str(numerator),
            "denominator": str(denominator),
        }
        duplicate["state"]["graph"]["coefficient"] = coefficient
        duplicate["state"]["graph"]["base_coefficient"] = coefficient
        duplicate["state"]["effective_coefficient"] = coefficient
        duplicates.append(duplicate)
    write_canvas_session(
        session_path,
        {"mode": "evaluate", "lines": [{"terms": duplicates}]},
    )

    resumed = ProjectorCanvasSession.load(session_path).open()

    assert len(resumed._term_editors) == 1  # type: ignore[attr-defined]
    assert resumed.current_projector_sum.coefficient(  # type: ignore[attr-defined]
        projector
    ) == Fraction(1, 2)
