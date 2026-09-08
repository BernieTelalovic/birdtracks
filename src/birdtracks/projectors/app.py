"""Local-browser launcher for the projector canvas."""

from __future__ import annotations

from importlib.util import find_spec
import inspect
import os
from pathlib import Path
import subprocess
import sys


def should_launch_canvas_app() -> bool:
    """Return whether ``Projector.create`` was called from a CLI context."""
    try:
        shell = get_ipython()  # type: ignore[name-defined]
    except NameError:
        shell = None
    if shell is not None:
        return shell.__class__.__name__ == "TerminalInteractiveShell"
    if hasattr(sys, "ps1"):
        return True
    frame = inspect.currentframe()
    caller = frame.f_back if frame is not None else None
    while caller is not None and str(caller.f_globals.get("__name__", "")).startswith(
        "birdtracks"
    ):
        caller = caller.f_back
    return caller is not None and caller.f_globals.get("__name__") == "__main__"


def launch_canvas_app(*, debug: bool = False) -> int:
    """Run the complete canvas locally in the user's default browser."""
    if find_spec("voila") is None:
        raise ImportError(
            "the browser canvas requires: pip install 'birdtracks[app]'"
        )
    entry = Path(__file__).with_name("canvas_app.py")
    environment = os.environ.copy()
    environment["BIRDTRACKS_EXPRESSION_ROOT"] = str(Path.cwd())
    environment["BIRDTRACKS_DEBUG"] = "1" if debug else "0"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "voila",
            str(entry),
            "--VoilaConfiguration.extension_language_mapping=.py=python",
            "--VoilaConfiguration.language_kernel_mapping=python=python3",
        ],
        check=False,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode


__all__ = ["launch_canvas_app"]
