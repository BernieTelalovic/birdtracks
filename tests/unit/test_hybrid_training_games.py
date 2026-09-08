"""Tests for separate resolver and exposure problem datasets."""

import json
from random import Random

from birdtracks import Antisymmetriser, Projector, Symmetriser
from birdtracks.projectors.detangle_training import DetangleState
from birdtracks.projectors.hybrid_training_games import (
    _append_problem,
    _exposure_target_to_data,
    _target_to_data,
    hybrid_dataset_overview,
    load_exposure_problems,
    load_resolver_problems,
    random_exposure_problem,
    random_resolver_problem,
)


def _state(projector: Projector) -> dict[str, object]:
    return DetangleState.from_projector(projector).configuration().state()


def test_version_one_resolver_dataset_recomputes_selected_target(tmp_path) -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((2, 3)),
        Antisymmetriser((1, 2)),
    ])
    path = tmp_path / "resolver.json"
    path.write_text(json.dumps({
        "format": "birdtracks-hybrid-training",
        "version": 1,
        "kind": "resolver",
        "examples": [{
            "phase": 1,
            "state": _state(projector),
            "summary": {"lines": 3, "nodes": 3, "layers": 3, "targets": 1,
                        "selected_support_union": 2},
        }],
    }))

    loaded = load_resolver_problems(path)

    assert loaded[0][0] == projector
    assert loaded[0][1].support_union_size == 2
    assert hybrid_dataset_overview(path)["kind"] == "resolver"


def test_version_two_resolver_dataset_requires_an_explicit_target(tmp_path) -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((2, 3)),
        Antisymmetriser((1, 2)),
    ])
    path = tmp_path / "resolver.json"
    _append_problem(path, "resolver", {
        "phase": 1,
        "state": _state(projector),
        "summary": {"lines": 3, "nodes": 3, "layers": 3, "targets": 1,
                    "selected_support_union": 2},
    })

    import pytest

    with pytest.raises(ValueError, match="no active-target data"):
        load_resolver_problems(path)


def test_resolver_dataset_preserves_an_explicit_nonleading_target(tmp_path) -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((2, 9)),
        Antisymmetriser((1, 2)),
        Symmetriser((3, 4, 5)),
        Symmetriser((4, 8)),
        Antisymmetriser((3, 4, 6)),
    ])
    from birdtracks.projectors.hybrid_simplification import find_sa_targets

    targets = find_sa_targets(projector)
    selected = targets[1]
    path = tmp_path / "resolver.json"
    _append_problem(path, "resolver", {
        "phase": 3,
        "state": _state(projector),
        "active_target": _target_to_data(selected),
        "summary": {"lines": 9, "nodes": 6, "layers": 6, "targets": 2,
                    "selected_support_union": selected.support_union_size},
    })

    loaded = load_resolver_problems(path)

    assert loaded == ((projector, selected),)
    assert loaded[0][1] != targets[0]


def test_resolver_dataset_rejects_active_connection_from_another_target(
    tmp_path,
) -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((2, 3)),
        Antisymmetriser((1, 2)),
    ])
    from birdtracks.projectors.hybrid_simplification import find_sa_targets

    target_data = _target_to_data(find_sa_targets(projector)[0])
    target_data["direct_path"]["source"][1] = 99
    path = tmp_path / "resolver.json"
    _append_problem(path, "resolver", {
        "phase": 1,
        "state": _state(projector),
        "active_target": target_data,
        "summary": {"lines": 3, "nodes": 3, "layers": 3, "targets": 1,
                    "selected_support_union": 2},
    })

    import pytest

    with pytest.raises(ValueError, match="does not belong"):
        load_resolver_problems(path)


def test_exposure_dataset_requires_no_existing_target(tmp_path) -> None:
    projector = Projector([
        Symmetriser((1, 2)),
        Symmetriser((1, 3)),
        Antisymmetriser((1, 4)),
    ])
    from birdtracks import find_sa_exposure_targets

    target = find_sa_exposure_targets(projector)[0]
    path = tmp_path / "exposure.json"
    _append_problem(path, "exposure", {
        "state": _state(projector),
        "active_target": _exposure_target_to_data(target),
        "summary": {"lines": 4, "nodes": 3, "layers": 3, "targets": 0,
                    "selected_support_union": 3},
    })

    assert load_exposure_problems(path) == ((projector, target),)


def test_random_resolver_problems_are_conditioned_and_not_immediate_zero() -> None:
    from birdtracks.projectors.hybrid_simplification import find_sa_targets

    for seed in range(12):
        projector, target = random_resolver_problem(
            Random(20 + seed),
            minimum_lines=4,
            maximum_lines=14,
            minimum_layers=4,
            maximum_layers=10,
        )

        assert target in find_sa_targets(projector)
        assert projector.simplify()
        assert 4 <= len(projector.support) <= 14
        assert 4 <= len(projector.layers) <= 10
        assert set(target.nodes) == {0, len(projector.nodes) - 1}
        assert set(target.nodes) == {
            projector.layers[0][0], projector.layers[-1][0]
        }


def test_random_exposure_problems_have_both_types_and_are_not_zero() -> None:
    from birdtracks import find_sa_exposure_targets
    from birdtracks.projectors.hybrid_simplification import find_sa_targets

    for seed in range(12):
        projector, target = random_exposure_problem(
            Random(30 + seed),
            minimum_lines=4,
            maximum_lines=14,
            minimum_layers=4,
            maximum_layers=10,
        )

        assert not find_sa_targets(projector)
        assert target in find_sa_exposure_targets(projector)
        assert all(not path.direct for path in target.obstructed_paths)
        assert projector.simplify()
        assert any(isinstance(node, Symmetriser) for node in projector.nodes)
        assert any(isinstance(node, Antisymmetriser) for node in projector.nodes)
        layer_of = {
            node: layer
            for layer, nodes in enumerate(projector.layers)
            for node in nodes
        }
        assert abs(layer_of[target.nodes[0]] - layer_of[target.nodes[1]]) >= 2
