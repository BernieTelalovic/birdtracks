"""Tests for the self-contained application entry point."""

import json
from pathlib import Path

from birdtracks.projectors import standalone


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


def test_standalone_version_does_not_start_server(capsys) -> None:
    assert standalone.main(["--version"]) == 0
    assert capsys.readouterr().out.strip()


def test_standalone_self_test_checks_runtime(capsys) -> None:
    assert standalone.main(["--self-test"]) == 0
    assert "runtime is ready" in capsys.readouterr().out


def test_standalone_rejects_unknown_arguments() -> None:
    try:
        standalone.main(["--unknown"])
    except SystemExit as error:
        assert "unknown Birdtracks argument" in str(error)
    else:
        raise AssertionError("unknown standalone arguments must fail")
