"""Tests for canonical whiteboard sidecar persistence."""

from fractions import Fraction
import json

import pytest

from birdtracks import (
    Antisymmetriser,
    NodePort,
    Permutation,
    PermutationNode,
    Projector,
    ProjectorSum,
    Symmetriser,
    whiteboard,
)
from birdtracks.young_diagrams import PairExpression, PairTerm
from birdtracks.projectors.whiteboard import (
    DiagramValueCodec,
    EvaluationEnvironment,
    ProjectorValueCodec,
    TypedWhiteboardSidecar,
    WhiteboardSidecar,
    WhiteboardStores,
    diagram_backend,
    diagram_codec,
    projector_codec,
    projector_backend,
    write_sidecar,
    write_typed_sidecar,
)


def example_projector() -> Projector:
    return Projector(
        [
            Antisymmetriser((1, 2)),
            PermutationNode(Permutation.from_cycle(1, 2), support=(1, 2)),
            Symmetriser((1, 2)),
        ],
        connections=None,
        coefficient=Fraction(-2, 3),
        input_boundary={1: NodePort(2, 1), 2: NodePort(2, 2)},
        output_boundary={1: NodePort(0, 1), 2: NodePort(0, 2)},
        port_orders={
            0: {"input": (1, 2), "output": (2, 1)},
            1: {"input": (1, 2), "output": (1, 2)},
            2: {"input": (2, 1), "output": (1, 2)},
        },
    )


def test_projector_codec_round_trips_topology_without_layout() -> None:
    projector = example_projector()

    restored = ProjectorValueCodec().decode(ProjectorValueCodec().encode(projector))

    assert restored == projector
    assert restored.coefficient == projector.coefficient
    assert restored.connections == projector.connections
    assert restored.port_orders_are_explicit


def test_sidecar_round_trips_definitions_and_frontend_document(tmp_path) -> None:
    environment = EvaluationEnvironment(projector_backend)
    environment.define("P2", Projector([Symmetriser({2, 3})]))
    environment.define("P1", example_projector())
    path = tmp_path / "session"

    saved = write_sidecar(
        path,
        environment,
        codec=projector_codec,
        document={"active_canvas": "main", "zoom": 1.25},
    )
    loaded = WhiteboardSidecar.load(
        path,
        backend=projector_backend,
        codec=projector_codec,
    )

    assert saved.path == loaded.path == tmp_path / "session.whiteboard"
    assert [item.name for item in loaded.environment.definitions] == ["P1", "P2"]
    assert loaded.environment.resolve("P1") == environment.resolve("P1")
    assert loaded.document == {"active_canvas": "main", "zoom": 1.25}

    raw = json.loads(saved.path.read_text(encoding="utf-8"))
    assert raw["format"] == "birdtracks-whiteboard"
    assert raw["version"] == 1
    assert "positions" not in raw["definitions"][0]["value"]


def test_sidecar_rejects_another_backend_or_codec(tmp_path) -> None:
    environment = EvaluationEnvironment(projector_backend)
    environment.define("P1", Projector([]))
    path = tmp_path / "session"
    write_sidecar(path, environment, codec=projector_codec)

    class OtherCodec:
        name = "other"

        def encode(self, value: Projector) -> dict[str, object]:
            return {}

        def decode(self, payload: object) -> Projector:
            return Projector([])

    with pytest.raises(ValueError, match="another value codec"):
        WhiteboardSidecar.load(
            path,
            backend=projector_backend,
            codec=OtherCodec(),
        )


def test_legacy_whiteboard_json_path_remains_loadable(tmp_path) -> None:
    environment = EvaluationEnvironment(projector_backend)
    environment.define("P1", Projector([]))
    legacy_path = tmp_path / "legacy.whiteboard.json"
    write_sidecar(legacy_path, environment, codec=projector_codec)

    loaded = WhiteboardSidecar.load(
        legacy_path,
        backend=projector_backend,
        codec=projector_codec,
    )

    assert loaded.path == legacy_path
    assert loaded.environment.resolve("P1") == Projector([])


def test_sidecar_rejects_duplicate_definitions(tmp_path) -> None:
    path = tmp_path / "duplicate.whiteboard.json"
    path.write_text(
        json.dumps(
            {
                "format": "birdtracks-whiteboard",
                "version": 1,
                "backend": "projector",
                "codec": "projector-v1",
                "definitions": [
                    {"name": "P1", "value": projector_codec.encode(Projector([]))},
                    {"name": "P1", "value": projector_codec.encode(Projector([]))},
                ],
                "document": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already defined"):
        WhiteboardSidecar.load(
            path,
            backend=projector_backend,
            codec=projector_codec,
        )


def test_typed_sidecar_keeps_projector_and_diagram_definitions_separate(tmp_path) -> None:
    projectors = EvaluationEnvironment(projector_backend)
    diagrams = EvaluationEnvironment(diagram_backend)
    projector = example_projector()
    diagram = PairExpression()
    projectors.define(r"\mathcal{P}_{1}", projector)
    diagrams.define(r"D_{1}", diagram)

    saved = write_typed_sidecar(
        tmp_path / "typed",
        WhiteboardStores(projectors=projectors, diagrams=diagrams),
        projector_backend=projector_backend,
        projector_codec=projector_codec,
        diagram_backend=diagram_backend,
        diagram_codec=diagram_codec,
        document={
            "lines": [
                {"kind": "projector", "source": r"\mathcal{P}_{1} := \birdtracks"},
                {"kind": "diagram", "source": r"D_{1} := \Diagram"},
            ]
        },
    )
    restored = TypedWhiteboardSidecar.load(
        saved.path,
        projector_backend=projector_backend,
        projector_codec=ProjectorValueCodec(),
        diagram_backend=diagram_backend,
        diagram_codec=DiagramValueCodec(),
    )

    assert restored.stores.projectors.resolve(r"\mathcal{P}_{1}") == projector
    assert restored.stores.diagrams.resolve(r"D_{1}") == diagram
    assert restored.document["lines"][0]["kind"] == "projector"
    assert restored.document["lines"][1]["kind"] == "diagram"
    raw = json.loads(saved.path.read_text(encoding="utf-8"))
    assert set(raw["stores"]) == {"projectors", "diagrams"}


def test_canvas_session_uses_whiteboard_sidecar_and_restores_environment(tmp_path) -> None:
    from birdtracks.projectors.canvas_session import (
        ProjectorCanvasSession,
        write_canvas_session,
    )

    environment = EvaluationEnvironment(projector_backend)
    projector = Projector([Symmetriser({1, 2})])
    environment.define("P1", projector)
    path = tmp_path / "canvas.canvas.json"
    write_canvas_session(
        path,
        {"mode": "evaluate", "lines": [{"terms": []}]},
        environment=environment,
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    restored = ProjectorCanvasSession.load(path)

    assert raw["format"] == "birdtracks-whiteboard"
    assert restored.environment.resolve("P1") == projector  # type: ignore[attr-defined]


def test_standalone_whiteboard_restores_source_blocks(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "formatted", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"$$P_1 := \frac{1}{2}$$"},
        {"id": "text-2", "source": r"Inline $P_1$ text"},
    ]

    raw = json.loads(
        (tmp_path / "formatted.whiteboard").read_text(encoding="utf-8")
    )
    assert raw["version"] == 2
    assert raw["document"]["title"] == "formatted"
    assert raw["document"]["blocks"] == document.blocks

    reopened = whiteboard(tmp_path / "formatted", debug=True)
    assert reopened.title == "formatted"  # type: ignore[attr-defined]
    assert reopened.blocks == document.blocks  # type: ignore[attr-defined]


def test_standalone_whiteboard_export_writes_neighbouring_tex_file(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "formatted", debug=True)
    document.blocks = [{"id": "text-1", "source": "x"}]  # type: ignore[attr-defined]
    document.export_request = 1  # type: ignore[attr-defined]

    export = tmp_path / "formatted.tex"
    assert export.exists()
    assert "\\documentclass" in export.read_text(encoding="utf-8")


def test_whiteboard_materialises_projector_markers_as_embedded_editors(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "embedded", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"P_1 := \birdtracks"},
    ]

    assert document.embedded_projector_ids == ["text-1:projector:0"]  # type: ignore[attr-defined]
    assert len(document.embedded_projectors) == 1  # type: ignore[attr-defined]
    assert document.embedded_projectors[0].widget_role == "embedded"  # type: ignore[attr-defined]
    assert document.embedded_projectors[0].mode == "create"  # type: ignore[attr-defined]
    assert document.embedded_projectors[0].graph["geometry"]["coefficient_space"] == 0.0  # type: ignore[attr-defined]
    json.dumps(document.get_state())

    document.blocks = [{"id": "text-1", "source": "P_1"}]  # type: ignore[attr-defined]
    assert document.embedded_projector_ids == []  # type: ignore[attr-defined]


def test_whiteboard_restores_saved_definition_without_evaluating_it(tmp_path) -> None:
    pytest.importorskip("anywidget")

    path = tmp_path / "definition"
    projector = Projector([Symmetriser((1, 2, 3))])
    document = whiteboard(path, debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"P \def \birdtracks"},
    ]
    editor = document.embedded_projectors[0]  # type: ignore[attr-defined]
    editor._configured_projector = projector
    editor.saved_revision = 1

    reopened = whiteboard(path, debug=True)

    assert reopened.embedded_projectors[0].projector == projector  # type: ignore[attr-defined]
    assert reopened.embedded_projectors[0].graph["nodes"]  # type: ignore[attr-defined]


def test_whiteboard_round_trips_embedded_projector_snapshot(tmp_path) -> None:
    pytest.importorskip("anywidget")
    from birdtracks.projectors.widget import projector_widget

    path = tmp_path / "snapshot"
    projector = Projector([Symmetriser((1, 2))])
    saved = projector_widget(projector, embedded=True)
    snapshot = {
        "revision": 1,
        "graph": saved.graph,
        "positions": saved.positions,
        "port_orders": saved.port_orders,
        "free_levels": saved.free_levels,
        "boundary_orders": saved.boundary_orders,
        "line_colors": {"right-anchor:0->input:0:1": "#ff0000"},
        "effective_coefficient": saved.effective_coefficient,
    }
    document = whiteboard(path, debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"P \def \birdtracks"},
    ]
    document.embedded_projectors[0].save_snapshot = snapshot  # type: ignore[attr-defined]

    raw = json.loads((tmp_path / "snapshot.whiteboard").read_text())
    assert raw["document"]["blocks"][0]["projector_snapshots"]["0"] == snapshot

    reopened = whiteboard(path, debug=True)
    restored = reopened.embedded_projectors[0]  # type: ignore[attr-defined]
    assert restored.projector == projector
    assert restored.line_colors == snapshot["line_colors"]


def test_whiteboard_restores_saved_pair_definition_without_evaluating_it(
    tmp_path,
) -> None:
    pytest.importorskip("anywidget")

    expression = PairExpression((PairTerm(unbarred=(2, 1), n0=2),))
    diagrams = EvaluationEnvironment(diagram_backend)
    diagrams.define("P", expression)
    path = tmp_path / "pair-definition"
    write_typed_sidecar(
        path,
        WhiteboardStores(
            projectors=EvaluationEnvironment(projector_backend),
            diagrams=diagrams,
        ),
        projector_backend=projector_backend,
        projector_codec=projector_codec,
        diagram_backend=diagram_backend,
        diagram_codec=diagram_codec,
        document={
            "title": "pair-definition",
            "blocks": [{"id": "text-1", "source": r"P \def \pair"}],
        },
    )

    reopened = whiteboard(path, debug=True)

    assert PairExpression.from_state(
        reopened.embedded_pairs[0].pair_expression  # type: ignore[attr-defined]
    ) == expression


def test_whiteboard_round_trips_embedded_pair_snapshot(tmp_path) -> None:
    pytest.importorskip("anywidget")

    path = tmp_path / "pair-snapshot"
    expression = PairExpression((PairTerm(barred=(1,), unbarred=(2,), n0=2),))
    document = whiteboard(path, debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"P \def \pair"},
    ]
    document.embedded_pairs[0].pair_expression = expression.state()  # type: ignore[attr-defined]

    raw = json.loads((tmp_path / "pair-snapshot.whiteboard").read_text())
    assert raw["document"]["blocks"][0]["pair_snapshots"]["0"] == expression.state()

    reopened = whiteboard(path, debug=True)
    assert PairExpression.from_state(
        reopened.embedded_pairs[0].pair_expression  # type: ignore[attr-defined]
    ) == expression


def test_whiteboard_simplification_locks_and_restores_connected_lines(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "simplification", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"X \def \birdtracks"},
    ]
    editor = document.embedded_projectors[0]  # type: ignore[attr-defined]
    editor._configured_projector = Projector([Symmetriser((1, 2, 3))])
    editor.saved_revision = 1
    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": "text-1", "action": "evaluate", "revision": 1,
    }

    assert document.blocks[0]["read_only"] is True  # type: ignore[attr-defined]
    assert editor.mode == "evaluate"
    assert document.blocks[-1]["calculation_step"] == 1  # type: ignore[attr-defined]
    assert len(document.blocks[-1]["calculation_terms"]) == 1  # type: ignore[attr-defined]

    # Generated equality lines must not become input to the expression parser.
    document.simplify_request = {
        "line_id": "text-1", "action": "evaluate", "revision": 2,
    }
    assert document.blocks[-1]["calculation_step"] == 2
    assert document.calculation_feedback.get("action") != "rejected"

    generated_id = document.blocks[-1]["id"]  # type: ignore[attr-defined]
    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": generated_id, "action": "restore", "revision": 3,
    }
    assert len(document.blocks) == 1  # type: ignore[attr-defined]
    assert "read_only" not in document.blocks[0]  # type: ignore[attr-defined]
    assert editor.mode == "create"


@pytest.mark.parametrize(
    ("projector", "source"),
    [
        (
            Projector([PermutationNode(Permutation.identity(), support=(1, 2))]),
            r"= N^{2}",
        ),
        (
            Projector([Symmetriser((1, 2)), Antisymmetriser((2, 3))]),
            r"= \frac{1}{4}N^{3} - \frac{1}{4}N",
        ),
    ],
)
def test_whiteboard_trace_evaluates_an_assigned_projector(
    tmp_path, projector, source,
) -> None:
    pytest.importorskip("anywidget")
    from birdtracks.projectors.widget import projector_widget

    document = whiteboard(tmp_path / "trace", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "definition", "source": r"P \def \birdtracks"},
        {"id": "trace", "source": r"\tr\left(P\right)"},
    ]
    saved = projector_widget(projector, embedded=True)
    snapshot = {
        "revision": 1,
        "graph": saved.graph,
        "positions": saved.positions,
        "port_orders": saved.port_orders,
        "free_levels": saved.free_levels,
        "boundary_orders": saved.boundary_orders,
        "line_colors": saved.line_colors,
        "effective_coefficient": saved.effective_coefficient,
    }

    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": "trace", "action": "evaluate", "revision": 1,
        "snapshots": {"definition:projector:0": snapshot},
    }

    result = document.blocks[-1]  # type: ignore[attr-defined]
    assert result["calculation_scalar"] is True
    assert result["source"] == source


def test_whiteboard_manual_expansion_appends_a_new_calculation_line(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "manual-expansion", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"X \def \birdtracks"},
    ]
    editor = document.embedded_projectors[0]  # type: ignore[attr-defined]
    editor._configured_projector = Projector([Symmetriser((1, 2, 3))])
    editor.saved_revision = 1
    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": "text-1", "action": "evaluate", "revision": 1,
    }

    first_line = document.blocks[-1]  # type: ignore[attr-defined]
    child = document.backend_projectors[0]  # type: ignore[attr-defined]
    child.expand_node_request = {"node": 0, "revision": 1}

    assert document.blocks[-1]["calculation_step"] == 2  # type: ignore[attr-defined]
    assert len(document.blocks[-1]["calculation_terms"]) > len(  # type: ignore[attr-defined]
        first_line["calculation_terms"]
    )


def test_whiteboard_full_expansion_collects_equal_permutations(tmp_path) -> None:
    """Regression for S(1,2)A(2,3)S(1,2)A(2,3)S(1,2)."""
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "permutation-collection", debug=True)
    document.blocks = [{"id": "text-1", "source": r"X \def \birdtracks"}]
    editor = document.embedded_projectors[0]  # type: ignore[attr-defined]
    editor._configured_projector = Projector(
        [
            Symmetriser((1, 2)),
            Antisymmetriser((2, 3)),
            Symmetriser((1, 2)),
            Antisymmetriser((2, 3)),
            Symmetriser((1, 2)),
        ]
    )
    original = editor._configured_projector
    editor.saved_revision = 1
    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": "text-1", "action": "evaluate", "revision": 1,
    }

    revision = 1
    while True:
        generated = document.blocks[-1]  # type: ignore[attr-defined]
        prefix = f"{generated['id']}:backend:"
        children = dict(
            zip(
                document.backend_projector_ids,  # type: ignore[attr-defined]
                document.backend_projectors,  # type: ignore[attr-defined]
                strict=True,
            )
        )
        selected = next(
            (
                child
                for key, child in children.items()
                if key.startswith(prefix)
                and any(
                    isinstance(node, (Symmetriser, Antisymmetriser))
                    for node in child._source_projector.nodes
                )
            ),
            None,
        )
        if selected is None:
            break
        node_index = next(
            index
            for index, node in enumerate(selected._source_projector.nodes)
            if isinstance(node, (Symmetriser, Antisymmetriser))
        )
        revision += 1
        selected.expand_node_request = {"node": node_index, "revision": revision}

    value = projector_codec.decode(document.blocks[-1]["calculation_value"])  # type: ignore[attr-defined]
    assert isinstance(value, ProjectorSum)
    assert len(document.blocks[-1]["calculation_terms"]) == 6  # type: ignore[attr-defined]
    assert value.collapse() == original.collapse()


def test_result_source_uses_whiteboard_signs_fractions_and_distinct_spans() -> None:
    from birdtracks import ProjectorSum
    from birdtracks.projectors.whiteboard.widget import _result_source

    value = ProjectorSum([
        Projector([Symmetriser((1, 2))]) * Fraction(1, 2),
        Projector([Antisymmetriser((1, 2))]) * Fraction(2, 3),
    ])
    source, terms = _result_source(value)
    assert source.startswith('= ')
    assert '+ ' in source
    assert r'\frac{1}{2}' in source
    assert r'\frac{2}{3}' in source
    assert terms[0]['end'] < terms[1]['start']
    assert all(source[term['start']:term['end']] == 'R' for term in terms)
    assert ProjectorSum(projector_codec.decode(term['value']) for term in terms) == value
    assert _result_source(ProjectorSum())[0] == '= 0'


def test_generated_terms_inherit_parent_line_colors() -> None:
    from birdtracks import ProjectorSum
    from birdtracks.projectors.whiteboard.widget import (
        _calculation_color_map,
        _result_source,
    )

    value = Projector([Symmetriser((1, 2))])
    _source, terms = _result_source(ProjectorSum((value,)))

    inherited = _calculation_color_map(
        "calculation-group-1",
        terms,
        [(value, {"strand:1": "#ff0000"})],
    )

    assert inherited == {
        "calculation-group-1:backend:0": {"strand:1": "#ff0000"},
    }


def test_expansion_uses_saved_parent_port_labels(tmp_path):
    from birdtracks.projectors.widget import projector_widget

    document = whiteboard(tmp_path / "renumbered-expansion", debug=True)
    document.blocks = [{"id": "text-1", "source": r"\birdtracks"}]
    editor = document.embedded_projectors[0]
    editor._configured_projector = Projector([Symmetriser((10, 11))])
    editor.saved_revision = 1
    document.simplify_request = {"line_id": "text-1", "action": "evaluate", "revision": 1}
    child = document.backend_projectors[-1]
    saved = projector_widget(Projector([Symmetriser((1, 2))]), embedded=True)
    child.graph = saved.graph
    child.port_orders = saved.port_orders
    child.boundary_orders = saved.boundary_orders
    child.save_snapshot = {
        "revision": 1, "graph": saved.graph, "positions": saved.positions,
        "port_orders": saved.port_orders, "free_levels": saved.free_levels,
        "boundary_orders": saved.boundary_orders,
        "effective_coefficient": saved.effective_coefficient,
        "line_colors": {"right-anchor:0->input:0:1": "#ff0000"},
    }
    child.expand_node_request = {"node": 0, "revision": 1}
    result = document.blocks[-1]
    assert result["calculation_step"] == 2
    for key, descendant in zip(document.backend_projector_ids, document.backend_projectors):
        if key.startswith(result['id'] + ':'):
            assert len(descendant.line_colors) == 1
            assert next(iter(descendant.line_colors)).startswith("right-anchor:0->left-anchor:")


@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("side", ["input", "output"])
def test_expansion_extends_color_to_entire_visible_line(tmp_path, recursive, side):
    from birdtracks.projectors.display_graph import compile_display_graph

    document = whiteboard(tmp_path / "expanded-colors", debug=True)
    document.blocks = [{"id": "text-1", "source": r"\birdtracks"}]
    editor = document.embedded_projectors[0]
    editor._configured_projector = Projector([Symmetriser((1, 2, 3))])
    editor.saved_revision = 1
    document.simplify_request = {"line_id": "text-1", "action": "evaluate", "revision": 1}
    child = document.backend_projectors[-1]
    key = ("right-anchor:2->input:0:3" if side == "input"
           else "output:0:3->left-anchor:2")
    child.line_colors = {key: "#ff0000"}
    child.expand_node_request = {"node": 0, "revision": 1,
                                **({"recursive_edge": "bottom"} if recursive else {})}
    generated = document.blocks[-1]
    assert generated["calculation_step"] == 2
    children = dict(zip(document.backend_projector_ids, document.backend_projectors))
    for index, term in enumerate(generated["calculation_terms"]):
        value = projector_codec.decode(term["value"])
        strands = compile_display_graph(value).strands
        strand = next(s for s in strands if
                      (s.source.kind == "right_boundary" and s.source.label == 3
                       if side == "input" else
                       s.target.kind == "left_boundary" and s.target.label == 3))

        def endpoint(e):
            if e.node is None:
                return f"{'right' if e.kind == 'right_boundary' else 'left'}-anchor:{e.label - 1}"
            return f"{'input' if e.kind == 'operator_input' else 'output'}:{e.node}:{e.label}"

        expected = {f"{endpoint(strand.source)}->{endpoint(strand.target)}": "#ff0000"}
        assert children[f"{generated['id']}:backend:{index}"].line_colors == expected


def test_shift_enter_snapshot_colors_reach_generated_projector(tmp_path) -> None:
    pytest.importorskip("anywidget")
    value = Projector([Symmetriser((1, 2))])
    source_editor = value.evaluate()._term_editors[0]  # type: ignore[attr-defined]
    colors = {"right-anchor:0->input:0:1": "#ff0000"}
    snapshot = {
        "revision": 1,
        "graph": source_editor.graph,
        "positions": source_editor.positions,
        "port_orders": source_editor.port_orders,
        "free_levels": source_editor.free_levels,
        "boundary_orders": source_editor.boundary_orders,
        "line_colors": colors,
        "effective_coefficient": source_editor.effective_coefficient,
    }
    document = whiteboard(tmp_path / "colored-shift-enter", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"X \def \birdtracks"},
    ]

    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": "text-1",
        "action": "evaluate",
        "revision": 1,
        "snapshots": {"text-1:projector:0": snapshot},
    }

    generated = document.blocks[-1]  # type: ignore[attr-defined]
    generated_id = generated["id"]
    assert generated["backend_line_colors"] == {
        f"{generated_id}:backend:0": colors,
    }
    generated_key = f"{generated_id}:backend:0"
    child_by_id = dict(zip(
        document.backend_projector_ids,  # type: ignore[attr-defined]
        document.backend_projectors,  # type: ignore[attr-defined]
        strict=True,
    ))
    assert child_by_id[generated_key].line_colors == colors


def test_whiteboard_rejects_non_sequential_equals_simplification(tmp_path, caplog) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "equation", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": "A = B"},
    ]
    document.simplify_request = {  # type: ignore[attr-defined]
        "line_id": "text-1", "action": "evaluate", "revision": 1,
    }

    assert "non-sequential simplification" in caplog.text
    assert document.calculation_feedback["action"] == "rejected"  # type: ignore[attr-defined]
    assert "read_only" not in document.blocks[0]  # type: ignore[attr-defined]


def test_whiteboard_recreates_deleted_projector_editor(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "recreate", debug=True)
    marker = r"P_1 := \birdtracks"
    document.blocks = [{"id": "text-1", "source": marker}]  # type: ignore[attr-defined]
    deleted = document.embedded_projectors[0]  # type: ignore[attr-defined]
    deleted.graph = {**deleted.graph, "sentinel": True}  # type: ignore[attr-defined]

    document.blocks = [{"id": "text-1", "source": "P_1"}]  # type: ignore[attr-defined]
    document.blocks = [{"id": "text-1", "source": marker}]  # type: ignore[attr-defined]

    recreated = document.embedded_projectors[0]  # type: ignore[attr-defined]
    assert recreated is not deleted
    assert "sentinel" not in recreated.graph  # type: ignore[attr-defined]


def test_whiteboard_uses_lowercase_projector_marker_only(tmp_path) -> None:
    pytest.importorskip("anywidget")

    document = whiteboard(tmp_path / "lowercase-marker", debug=True)
    document.blocks = [  # type: ignore[attr-defined]
        {"id": "text-1", "source": r"P_1 := \Projector{"},
    ]

    assert document.embedded_projector_ids == []  # type: ignore[attr-defined]


def test_untitled_whiteboard_stays_in_memory_until_named(tmp_path, monkeypatch) -> None:
    pytest.importorskip("anywidget")

    monkeypatch.chdir(tmp_path)
    document = whiteboard(debug=True)
    document.blocks = [{"id": "text-1", "source": "draft"}]  # type: ignore[attr-defined]

    assert not (tmp_path / "expressions").exists()

    document.title = "My Notes"  # type: ignore[attr-defined]

    path = tmp_path / "expressions" / "My Notes.whiteboard"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["document"]["title"] == "My Notes"
    assert raw["document"]["blocks"] == document.blocks


def test_saving_untitled_whiteboard_assigns_next_available_name(
    tmp_path, monkeypatch
) -> None:
    pytest.importorskip("anywidget")

    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "expressions" / "Untitled_1.whiteboard"
    existing.parent.mkdir()
    existing.write_text("reserved", encoding="utf-8")
    document = whiteboard(debug=True)

    document.save_request += 1  # type: ignore[attr-defined]

    path = tmp_path / "expressions" / "Untitled_2.whiteboard"
    assert document.title == "Untitled_2"  # type: ignore[attr-defined]
    assert document.session == path  # type: ignore[attr-defined]
    assert path.exists()


def test_whiteboard_workspace_adds_an_independent_untitled_document() -> None:
    pytest.importorskip("anywidget")

    from birdtracks.projectors.whiteboard.widget import whiteboard_workspace

    workspace = whiteboard_workspace(debug=True)
    first = workspace.documents[0]

    workspace.new_document_request += 1

    assert len(workspace.documents) == 2
    assert workspace.active_index == 1
    assert workspace.documents[0] is first
    assert workspace.documents[1] is not first
    assert workspace.documents[1].title == ""
    assert workspace.documents[1].session is None


def test_whiteboard_workspace_closes_tabs_and_keeps_one_document() -> None:
    pytest.importorskip("anywidget")

    from birdtracks.projectors.whiteboard.widget import whiteboard_workspace

    workspace = whiteboard_workspace(debug=True)
    workspace.new_document_request += 1
    remaining = workspace.documents[0]

    workspace.close_document_request = 1
    workspace.close_document_revision += 1
    assert workspace.documents == [remaining]
    assert workspace.active_index == 0

    workspace.close_document_request = 0
    workspace.close_document_revision += 1
    assert len(workspace.documents) == 1
    assert workspace.documents[0] is not remaining


def test_whiteboard_workspace_loads_uploaded_document(tmp_path, monkeypatch) -> None:
    pytest.importorskip("anywidget")

    from birdtracks.projectors.whiteboard.widget import whiteboard_workspace

    monkeypatch.chdir(tmp_path)
    source = whiteboard(tmp_path / "source.whiteboard", debug=True)
    source.title = "Loaded board"
    source.blocks = [{"id": "text-1", "source": "1 + 1"}]
    content = source.session.read_text(encoding="utf-8")
    workspace = whiteboard_workspace(debug=True)

    workspace.documents[0].load_document_request = {
        "name": "source.whiteboard",
        "content": content,
        "revision": 1,
    }

    assert len(workspace.documents) == 2
    assert workspace.active_index == 1
    assert workspace.documents[1].title == "Loaded board"
    assert workspace.documents[1].blocks == [{"id": "text-1", "source": "1 + 1"}]


def test_whiteboard_workspace_saves_new_document_beside_opened_session(tmp_path) -> None:
    pytest.importorskip("anywidget")

    from birdtracks.projectors.whiteboard.widget import whiteboard_workspace

    workspace = whiteboard_workspace(tmp_path / "notes" / "original", debug=True)
    workspace.new_document_request += 1
    document = workspace.documents[1]
    document.title = "follow-up"

    assert document.session == tmp_path / "notes" / "follow-up.whiteboard"
    assert document.session.exists()


def test_whiteboard_and_projector_canvas_have_independent_session_files(
    tmp_path, monkeypatch
) -> None:
    pytest.importorskip("anywidget")

    from birdtracks import Projector

    monkeypatch.chdir(tmp_path)
    whiteboard("shared-name", debug=True)
    Projector.create(session="shared-name", detangler=False)

    assert (tmp_path / "expressions" / "shared-name.whiteboard").exists()
    assert (tmp_path / "expressions" / "shared-name.canvas.json").exists()
