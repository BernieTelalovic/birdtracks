"""Tests for the optional local-browser canvas launcher."""

from types import SimpleNamespace

import pytest

import birdtracks
from birdtracks.projectors import app


def test_top_level_create_builds_canvas_outside_cli_context() -> None:
    pytest.importorskip("anywidget")
    canvas = birdtracks.create(detangler=False)

    assert canvas.mode == "create"
    assert len(canvas._term_editors) == 1


def test_create_from_command_line_main_launches_browser_app(monkeypatch) -> None:
    launched: list[bool] = []
    monkeypatch.setattr(
        app,
        "launch_canvas_app",
        lambda **kwargs: launched.append(kwargs["debug"]) or 0,
    )

    namespace = {"__name__": "__main__", "birdtracks": birdtracks}
    exec("result = birdtracks.create()", namespace)

    assert launched == [False]
    assert namespace["result"] == 0


def test_launcher_uses_packaged_python_entry_point(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(app, "find_spec", lambda name: object())
    monkeypatch.setattr(
        app.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0),
    )

    assert app.launch_canvas_app() == 0
    command, kwargs = calls[0]
    assert command[:3] == [app.sys.executable, "-m", "voila"]
    assert command[3].endswith("canvas_app.py")
    assert "--VoilaConfiguration.extension_language_mapping=.py=python" in command
    assert kwargs["stdout"] is app.subprocess.DEVNULL
    assert kwargs["stderr"] is app.subprocess.DEVNULL
    assert kwargs["env"]["BIRDTRACKS_EXPRESSION_ROOT"] == str(app.Path.cwd())
    assert kwargs["env"]["BIRDTRACKS_DEBUG"] == "0"


def test_create_forwards_debug_to_browser_app(monkeypatch) -> None:
    launched: list[bool] = []
    monkeypatch.setattr(
        app,
        "launch_canvas_app",
        lambda **kwargs: launched.append(kwargs["debug"]) or 0,
    )

    namespace = {"__name__": "__main__", "birdtracks": birdtracks}
    exec("result = birdtracks.create(debug=True)", namespace)

    assert launched == [True]


def test_launcher_reports_missing_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr(app, "find_spec", lambda name: None)

    try:
        app.launch_canvas_app()
    except ImportError as error:
        assert "birdtracks[app]" in str(error)
    else:
        raise AssertionError("missing Voilà must raise ImportError")
