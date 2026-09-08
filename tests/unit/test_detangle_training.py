"""Tests for the optional learned-detangler environment and data generator."""

from math import isfinite
from random import Random

import pytest

from birdtracks.projectors.detangle_training import (
    DETANGLER_SCHEMA_VERSION,
    FEATURE_COUNT,
    DetangleAction,
    DetangleState,
    LearnedDetangler,
    beam_search_detangle,
    greedy_detangle,
    random_projector,
)
from birdtracks import (
    Antisymmetriser,
    Permutation,
    PermutationNode,
    Projector,
    Symmetriser,
)


def test_random_projectors_are_valid_deterministic_layered_graphs() -> None:
    first = random_projector(Random(19), strands=9, layers=5)
    second = random_projector(Random(19), strands=9, layers=5)

    assert first == second
    assert len(first.layers) == 5
    assert first.support == frozenset(range(1, 10))
    assert first.input_boundary.keys() == first.output_boundary.keys()


def test_every_training_action_preserves_the_projector_topology() -> None:
    projector = random_projector(Random(4), strands=8, layers=4)
    state = DetangleState.random_layout(projector, Random(11))

    for action in state.legal_actions():
        moved = state.apply(action)
        assert moved.projector is projector
        assert isfinite(moved.metrics().loss)
        assert len(moved.action_features(action)) == FEATURE_COUNT
        assert len(moved.value_features()) == FEATURE_COUNT


def test_actions_move_units_and_ports_directly_across_multiple_slots() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2, 3)),
            Antisymmetriser((4, 5)),
            Symmetriser((6, 7)),
        ]
    )
    state = DetangleState.from_projector(projector)

    moved_layer = state.apply(DetangleAction("layer", 0, 0, 2))
    moved_port = state.apply(DetangleAction("input", 0, 0, 2))

    assert moved_layer.layer_orders[0] == (
        state.layer_orders[0][1],
        state.layer_orders[0][2],
        state.layer_orders[0][0],
    )
    assert moved_port.port_orders[0][0] == (2, 3, 1)
    assert moved_layer.projector is projector
    assert moved_port.projector is projector


def test_detangler_uses_visible_sa_columns_and_never_hidden_permutation_layers() -> None:
    projector = Projector(
        [
            Symmetriser((1, 2, 3)),
            PermutationNode(
                Permutation.from_cycle(1, 2), support=(1, 2, 3, 4)
            ),
            Antisymmetriser((1, 2, 3)),
        ]
    )

    state = DetangleState.from_projector(projector)

    assert len(projector.layers) == 3
    assert len(state.layer_orders) == 2
    assert all(("node", 1) not in layer for layer in state.layer_orders)
    assert all(
        not (action.kind in {"input", "output"} and action.owner == 1)
        for action in state.legal_actions()
    )
    assert all(("free", 4) in layer for layer in state.layer_orders)
    configuration = state.configuration()
    recovered = DetangleState.from_configuration(configuration)
    assert recovered.layer_orders == state.layer_orders
    assert recovered.projector == projector


def test_detangle_state_builds_an_equal_replayable_configuration() -> None:
    projector = random_projector(Random(81), strands=7, layers=4)
    state = DetangleState.random_layout(projector, Random(5))

    configured = state.configured_projector()
    configuration = state.configuration()

    assert configured == projector
    assert configuration.projector == projector
    assert configuration.state()["free_levels"]
    recovered = DetangleState.from_configuration(configuration)
    assert recovered.projector == state.projector
    assert recovered.layer_orders == state.layer_orders
    assert recovered.port_orders == state.port_orders


def test_exact_searches_preserve_topology_and_never_worsen_loss() -> None:
    projector = random_projector(Random(23), strands=5, layers=2)
    state = DetangleState.random_layout(projector, Random(29))

    greedy = greedy_detangle(state, max_moves=3)
    beam = beam_search_detangle(state, depth=2, beam_width=6)

    assert greedy.state.projector is projector
    assert beam.state.projector is projector
    assert greedy.metrics.loss <= greedy.initial_metrics.loss
    assert beam.metrics.loss <= beam.initial_metrics.loss
    assert set(beam.optimal_first_actions) <= set(state.legal_actions())


def test_beam_oracle_reports_all_exactly_tied_first_moves() -> None:
    state = DetangleState.from_projector(Projector([]))

    result = beam_search_detangle(state, depth=2, beam_width=2)

    assert result.actions == ()
    assert result.optimal_first_actions == (DetangleAction("stop"),)


def test_trained_policy_loads_and_only_accepts_improving_moves(tmp_path) -> None:
    torch = pytest.importorskip("torch")
    from torch import nn

    model = nn.Sequential(
        nn.Linear(FEATURE_COUNT, 4),
        nn.ReLU(),
        nn.Linear(4, 1),
    )
    checkpoint = tmp_path / "tiny.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_count": FEATURE_COUNT,
            "detangler_schema_version": DETANGLER_SCHEMA_VERSION,
            "hidden": 4,
            "depth": 1,
        },
        checkpoint,
    )
    projector = random_projector(Random(2), strands=6, layers=3)

    result = LearnedDetangler.load(checkpoint)(projector, max_moves=10)

    assert result.projector == projector
    assert result.metrics.loss <= result.initial_metrics.loss
    assert 0 <= result.steps <= 10


def test_old_display_schema_checkpoint_requires_retraining(tmp_path) -> None:
    torch = pytest.importorskip("torch")
    from torch import nn

    model = nn.Sequential(nn.Linear(FEATURE_COUNT, 1))
    checkpoint = tmp_path / "old-layout.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_count": FEATURE_COUNT,
            "hidden": 1,
            "depth": 1,
        },
        checkpoint,
    )

    with pytest.raises(ValueError, match="retrain"):
        LearnedDetangler.load(checkpoint)


def test_value_checkpoint_scores_layout_states_and_preserves_topology(
    tmp_path,
) -> None:
    torch = pytest.importorskip("torch")
    from torch import nn

    model = nn.Sequential(
        nn.Linear(FEATURE_COUNT, 4),
        nn.ReLU(),
        nn.Linear(4, 1),
    )
    for parameter in model.parameters():
        nn.init.zeros_(parameter)
    checkpoint = tmp_path / "value.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_count": FEATURE_COUNT,
            "detangler_schema_version": DETANGLER_SCHEMA_VERSION,
            "hidden": 4,
            "depth": 1,
            "model_kind": "layout_value_v1",
        },
        checkpoint,
    )
    projector = random_projector(Random(7), strands=5, layers=2)

    result = LearnedDetangler.load(checkpoint)(projector, max_moves=4)

    assert result.projector == projector
    assert result.metrics.loss <= result.initial_metrics.loss
    assert result.steps == 0


def test_evaluation_canvas_uses_policy_for_every_expanded_term(
    tmp_path, monkeypatch
) -> None:
    pytest.importorskip("anywidget")
    torch = pytest.importorskip("torch")
    from torch import nn

    model = nn.Sequential(
        nn.Linear(FEATURE_COUNT, 4),
        nn.ReLU(),
        nn.Linear(4, 1),
    )
    checkpoint = tmp_path / "canvas.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_count": FEATURE_COUNT,
            "detangler_schema_version": DETANGLER_SCHEMA_VERSION,
            "hidden": 4,
            "depth": 1,
        },
        checkpoint,
    )
    calls = []
    original = LearnedDetangler.optimize

    def recorded(self, projector, **kwargs):
        calls.append(projector)
        return original(self, projector, **kwargs)

    monkeypatch.setattr(LearnedDetangler, "optimize", recorded)
    projector = Projector([Symmetriser((1, 2))])
    canvas = projector.evaluate(detangler=checkpoint)

    canvas._term_editors[0].expand_node_request = {  # type: ignore[attr-defined]
        "node": 0,
        "revision": 1,
    }

    assert len(calls) == 2
    assert canvas._history[-1].collapse() == projector.collapse()  # type: ignore[attr-defined]


def test_evaluation_canvas_discovers_the_default_checkpoint(
    tmp_path, monkeypatch
) -> None:
    pytest.importorskip("anywidget")
    torch = pytest.importorskip("torch")
    from torch import nn
    from birdtracks.projectors import detangle_training

    model = nn.Sequential(
        nn.Linear(FEATURE_COUNT, 4),
        nn.ReLU(),
        nn.Linear(4, 1),
    )
    checkpoint = tmp_path / "detangler.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_count": FEATURE_COUNT,
            "detangler_schema_version": DETANGLER_SCHEMA_VERSION,
            "hidden": 4,
            "depth": 1,
        },
        checkpoint,
    )
    monkeypatch.setattr(
        detangle_training,
        "default_detangler_checkpoint",
        lambda: checkpoint,
    )

    canvas = Projector([Symmetriser((1, 2))]).evaluate()

    assert canvas._learned_detangler.checkpoint == checkpoint  # type: ignore[attr-defined]


def test_false_explicitly_disables_default_detangler(monkeypatch) -> None:
    pytest.importorskip("anywidget")
    from birdtracks.projectors import detangle_training

    monkeypatch.setattr(
        detangle_training,
        "default_detangler_checkpoint",
        lambda: object(),
    )

    canvas = Projector([Symmetriser((1, 2))]).evaluate(detangler=False)

    assert canvas._learned_detangler is None  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"strands": 3}, "four strands"),
        ({"layers": 0}, "positive"),
        ({"maximum_support": 1}, "at least two"),
    ],
)
def test_random_projector_rejects_invalid_sizes(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        random_projector(**kwargs)
