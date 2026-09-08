"""Tests for the self-contained application entry point."""

import json
from pathlib import Path
import tomllib

from birdtracks.projectors import standalone


def test_application_extras_install_kernel_runtime() -> None:
    project = tomllib.loads(
        (Path(__file__).parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    for extra in ("app", "coding", "standalone"):
        assert any(
            dependency.startswith("ipykernel")
            for dependency in project["optional-dependencies"][extra]
        )

    assert any(
        dependency.startswith("jupyterlab")
        for dependency in project["optional-dependencies"]["coding"]
    )


def test_runtime_kernelspec_restarts_bundled_executable(tmp_path: Path) -> None:
    kernel_directory = standalone._write_runtime_kernelspec(tmp_path)
    specification = json.loads(
        (kernel_directory / "kernel.json").read_text(encoding="utf-8")
    )

    assert specification["argv"] == [
        standalone.sys.executable,
        "--birdtracks-kernel",
        "-f",
        "{connection_file}",
    ]
    assert specification["language"] == "python"


def test_external_process_environment_restores_linux_library_path(monkeypatch) -> None:
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/birdtracks-bundle")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib:/usr/lib")

    environment = standalone._external_process_environment()

    assert environment["LD_LIBRARY_PATH"] == "/usr/local/lib:/usr/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in environment


def test_external_process_environment_removes_injected_path(monkeypatch) -> None:
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/birdtracks-bundle")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    assert "LD_LIBRARY_PATH" not in standalone._external_process_environment()


def test_linux_system_browser_uses_clean_environment(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        standalone.subprocess,
        "Popen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/birdtracks-bundle")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    assert standalone._LinuxSystemBrowser().open("http://127.0.0.1:1234")
    assert calls[0][0][0] == ["xdg-open", "http://127.0.0.1:1234"]
    assert "LD_LIBRARY_PATH" not in calls[0][1]["env"]


def test_standalone_version_does_not_start_server(capsys) -> None:
    assert standalone.main(["--version"]) == 0
    assert capsys.readouterr().out.strip()


def test_standalone_self_test_checks_runtime(capsys) -> None:
    assert standalone.main(["--self-test"]) == 0
    assert "runtime is ready" in capsys.readouterr().out


def test_standalone_self_test_supports_windowed_runtime(monkeypatch) -> None:
    monkeypatch.setattr(standalone.sys, "stdout", None)

    assert standalone.main(["--self-test"]) == 0


def test_standalone_rejects_unknown_arguments() -> None:
    try:
        standalone.main(["--unknown"])
    except SystemExit as error:
        assert "unknown Birdtracks argument" in str(error)
    else:
        raise AssertionError("unknown standalone arguments must fail")
