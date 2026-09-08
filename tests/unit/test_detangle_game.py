"""Tests for durable human detangling demonstrations."""

import json
from importlib import import_module
from inspect import signature
from random import Random

import pytest

from birdtracks import Antisymmetriser, Projector, Symmetriser

from birdtracks.projectors.detangle_game import (
    DATASET_FORMAT,
    _append_demonstration,
    _random_nonzero_projector,
    _read_dataset,
    detangle_game,
    load_detangle_demonstrations,
)


def test_game_defaults_to_four_through_ten_strands() -> None:
    parameters = signature(detangle_game).parameters

    assert parameters["min_strands"].default == 4
    assert parameters["max_strands"].default == 10


def test_game_rejects_exactly_annihilated_candidates(monkeypatch) -> None:
    zero = Projector(
        [Symmetriser((1, 2)), Antisymmetriser((1, 2))]
    )
    survivor = Projector([Symmetriser((1, 2))])
    candidates = iter((zero, survivor))
    game_module = import_module("birdtracks.projectors.detangle_game")
    monkeypatch.setattr(
        game_module,
        "random_projector",
        lambda *_args, **_kwargs: next(candidates),
    )

    selected = _random_nonzero_projector(
        Random(3),
        min_strands=4,
        max_strands=10,
        min_layers=2,
        max_layers=7,
        maximum_support=4,
    )

    assert selected is survivor


def test_demonstrations_append_to_a_traceable_versioned_dataset(tmp_path) -> None:
    destination = tmp_path / "human" / "examples.json"

    _append_demonstration(destination, {"round_seed": 3})
    _append_demonstration(destination, {"round_seed": 5})

    saved = json.loads(destination.read_text())
    assert saved["format"] == DATASET_FORMAT
    assert saved["version"] == 2
    assert saved["examples"] == [{"round_seed": 3}, {"round_seed": 5}]
    assert not destination.with_name(f".{destination.name}.tmp").exists()


def test_detangling_dataset_rejects_an_unrelated_json_file(tmp_path) -> None:
    destination = tmp_path / "wrong.json"
    destination.write_text('{"examples": []}')

    with pytest.raises(ValueError, match="not a compatible"):
        _read_dataset(destination)


def test_version_one_demonstrations_migrate_to_visible_layout_schema(tmp_path) -> None:
    destination = tmp_path / "old.json"
    destination.write_text(
        json.dumps({"format": DATASET_FORMAT, "version": 1, "examples": []})
    )

    migrated = _read_dataset(destination)

    assert migrated["version"] == 2


def test_game_save_records_a_round_and_opens_the_next_one(tmp_path) -> None:
    pytest.importorskip("anywidget")
    destination = tmp_path / "game.json"
    game = detangle_game(
        destination,
        seed=11,
        min_strands=4,
        max_strands=4,
        min_layers=1,
        max_layers=1,
    )
    body = game.children[2]
    canvas = body.children[0]
    editor = canvas._term_editors[0]

    canvas._save_step_button.click()
    editor.save_snapshot = {
        "revision": editor.save_command,
        "positions": editor.positions,
        "port_orders": editor.port_orders,
        "free_levels": editor.free_levels,
        "boundary_orders": editor.boundary_orders,
        "effective_coefficient": editor.effective_coefficient,
    }

    saved = _read_dataset(destination)
    assert len(saved["examples"]) == 1
    assert "initial" in saved["examples"][0]
    assert "final" in saved["examples"][0]
    assert body.children[0] is not canvas
    demonstrations = load_detangle_demonstrations(destination)
    assert len(demonstrations) == 1
    assert demonstrations[0][0].projector == demonstrations[0][1].projector
