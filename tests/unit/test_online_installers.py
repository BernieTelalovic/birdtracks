"""Static checks for the versioned online installer templates."""

from pathlib import Path


PACKAGING = Path(__file__).parents[2] / "packaging"


def test_installers_are_release_versioned() -> None:
    for name in (
        "install-birdtracks.sh.in",
        "install-birdtracks.ps1.in",
        "install-birdtracks.cmd.in",
    ):
        contents = (PACKAGING / name).read_text(encoding="utf-8")
        assert "__BIRDTRACKS_VERSION__" in contents


def test_installers_bootstrap_without_system_python_or_git() -> None:
    linux = (PACKAGING / "install-birdtracks.sh.in").read_text(encoding="utf-8")
    windows = (PACKAGING / "install-birdtracks.ps1.in").read_text(
        encoding="utf-8"
    )

    for contents in (linux, windows):
        assert "UV_PYTHON_INSTALL_DIR" in contents
        assert "tool install --force --python 3.12" in contents
        assert "birdtracks[coding]" in contents
        assert "archive/refs/tags/" in contents
        assert "git+" not in contents
