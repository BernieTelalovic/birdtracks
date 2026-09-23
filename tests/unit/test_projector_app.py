"""Tests for the optional local-browser canvas launcher."""

from types import SimpleNamespace

import pytest

import birdtracks
from birdtracks.projectors import app
from birdtracks.projectors.whiteboard import app as whiteboard_app


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


def test_whiteboard_launcher_passes_document_and_debug_to_voila(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    class Process:
        def __init__(self) -> None:
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self) -> None:
            self.running = False

        def wait(self, **kwargs):
            del kwargs
            return 0

    process = Process()
    monkeypatch.setattr(whiteboard_app, "find_spec", lambda name: object())
    monkeypatch.setattr(whiteboard_app, "_free_port", lambda: 12345)
    monkeypatch.setattr(whiteboard_app, "_wait_for_server", lambda *args: None)
    monkeypatch.setattr(whiteboard_app, "_ensure_linux_desktop_integration", lambda: None)
    monkeypatch.setattr(
        whiteboard_app.subprocess, "Popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or process,
    )
    window = SimpleNamespace(load_url=lambda url: calls.append((["load_url", url], {})))
    monkeypatch.setitem(
        whiteboard_app.sys.modules,
        "webview",
        SimpleNamespace(
            create_window=lambda *args, **kwargs: calls.append((list(args), kwargs)) or window,
            start=lambda **kwargs: calls.append((["start"], kwargs)),
        ),
    )

    assert whiteboard_app.launch_whiteboard_app("notes.whiteboard", debug=True) == 0
    command, kwargs = calls[0]
    assert command[:3] == [whiteboard_app.sys.executable, "-m", "voila"]
    assert command[3].endswith("whiteboard_app.py")
    assert "--Voila.open_browser=False" in command
    assert "--Voila.port=12345" in command
    assert kwargs["env"]["BIRDTRACKS_WHITEBOARD_SESSION"] == "notes.whiteboard"
    assert kwargs["env"]["BIRDTRACKS_DEBUG"] == "1"
    assert calls[1][0] == ["Birdtracks Whiteboard"]
    assert "Starting Birdtracks Whiteboard" in calls[1][1]["html"]
    assert calls[2][0] == ["start"]
    assert calls[2][1]["debug"] is True
    assert calls[2][1]["gui"] == (
        "qt" if whiteboard_app.sys.platform.startswith("linux") else None
    )
    assert callable(calls[2][1]["func"])
    assert not process.running


def test_whiteboard_launcher_reports_missing_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr(whiteboard_app, "find_spec", lambda name: None)

    with pytest.raises(ImportError, match=r"birdtracks\[app\]"):
        whiteboard_app.launch_whiteboard_app()


def test_whiteboard_asset_path_is_available_without_app_dependencies(capsys) -> None:
    assert whiteboard_app.main(["--asset-path", "birdtracks-whiteboard-file.svg"]) == 0
    assert capsys.readouterr().out.strip().endswith(
        "birdtracks-whiteboard-file.svg"
    )


def test_linux_desktop_integration_registers_active_launcher(
    tmp_path, monkeypatch
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(whiteboard_app.sys, "platform", "linux")
    monkeypatch.setattr(whiteboard_app.sys, "argv", ["birdtracks-whiteboard"])
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        whiteboard_app.shutil,
        "which",
        lambda name: None if name == "birdtracks-whiteboard" else "/bin/" + name,
    )
    monkeypatch.setattr(
        whiteboard_app.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command),
    )

    whiteboard_app._ensure_linux_desktop_integration()

    desktop = (tmp_path / "applications/birdtracks-whiteboard.desktop").read_text()
    assert "birdtracks.projectors.whiteboard.app" in desktop
    assert "Icon=birdtracks-whiteboard-projector" in desktop
    assert "MimeType=application/x-birdtracks-whiteboard;" in desktop
    assert (tmp_path / "mime/packages/birdtracks-whiteboard.xml").exists()
    app_icon = tmp_path / "icons/hicolor/scalable/apps/birdtracks-whiteboard-projector.svg"
    file_icon = (
        tmp_path
        / "icons/hicolor/scalable/mimetypes/birdtracks-whiteboard-file-projector.svg"
    )
    assert app_icon.read_bytes() == file_icon.read_bytes()
    assert commands[-1] == [
        "xdg-mime", "default", "birdtracks-whiteboard.desktop",
        "application/x-birdtracks-whiteboard",
    ]
