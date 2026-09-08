"""Launch the complete Birdtracks coding environment in JupyterLab."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    """Open JupyterLab in the current directory with Birdtracks available."""
    try:
        from jupyterlab.labapp import LabApp
    except ImportError as exc:
        raise SystemExit(
            "Birdtracks Lab is not installed. Install birdtracks[coding]."
        ) from exc

    LabApp.launch_instance(
        argv=[
            f"--ServerApp.root_dir={Path.cwd()}",
            "--ServerApp.open_browser=True",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
