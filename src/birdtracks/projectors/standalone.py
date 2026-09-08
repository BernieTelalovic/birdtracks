"""Entry point for the self-contained Birdtracks application."""

from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory


_KERNEL_ARGUMENT = "--birdtracks-kernel"


def _write_runtime_kernelspec(root: Path) -> Path:
    """Create a kernelspec which starts the bundled executable itself."""
    kernel_directory = root / "kernels" / "birdtracks"
    kernel_directory.mkdir(parents=True)
    (kernel_directory / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [
                    sys.executable,
                    _KERNEL_ARGUMENT,
                    "-f",
                    "{connection_file}",
                ],
                "display_name": "Birdtracks",
                "language": "python",
                "metadata": {"debugger": False},
            }
        ),
        encoding="utf-8",
    )
    return kernel_directory


def _run_kernel(arguments: list[str]) -> int:
    """Run ipykernel when Voilà starts a child copy of the executable."""
    sys.argv = ["ipykernel_launcher", *arguments]
    runpy.run_module("ipykernel_launcher", run_name="__main__")
    return 0


def _application_entry() -> Path:
    """Locate the bundled Voilà Python entry document."""
    packaged_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parents[2]))
    candidates = (
        packaged_root / "birdtracks" / "projectors" / "canvas_app.py",
        Path(__file__).with_name("canvas_app.py"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("the bundled Birdtracks canvas entry is missing")


def _run_application() -> int:
    """Start the private local Voilà server and open the default browser."""
    try:
        from voila.app import Voila
    except ImportError as exc:
        raise ImportError(
            "the browser calculator requires the birdtracks app dependencies"
        ) from exc

    os.environ["BIRDTRACKS_EXPRESSION_ROOT"] = str(Path.cwd())
    os.environ.setdefault("BIRDTRACKS_DEBUG", "0")
    with TemporaryDirectory(prefix="birdtracks-") as temporary:
        runtime = Path(temporary)
        _write_runtime_kernelspec(runtime)
        previous_jupyter_path = os.environ.get("JUPYTER_PATH")
        packaged_root = Path(getattr(sys, "_MEIPASS", Path(sys.prefix)))
        paths = [str(runtime), str(packaged_root / "share" / "jupyter")]
        if previous_jupyter_path:
            paths.append(previous_jupyter_path)
        os.environ["JUPYTER_PATH"] = os.pathsep.join(paths)
        Voila.launch_instance(
            argv=[
                str(_application_entry()),
                "--VoilaConfiguration.extension_language_mapping=.py=python",
                "--VoilaConfiguration.language_kernel_mapping=python=birdtracks",
                "--Voila.open_browser=True",
                "--ServerApp.ip=127.0.0.1",
                "--ServerApp.port=0",
                "--Application.log_level=CRITICAL",
            ]
        )
    return 0


def _self_test() -> int:
    """Verify the modules and resources required by the bundled app."""
    import anywidget  # noqa: F401
    import birdtracks  # noqa: F401
    import igraph  # noqa: F401
    import ipykernel  # noqa: F401
    import voila  # noqa: F401

    _application_entry()
    with TemporaryDirectory(prefix="birdtracks-test-") as temporary:
        specification = _write_runtime_kernelspec(Path(temporary))
        json.loads((specification / "kernel.json").read_text(encoding="utf-8"))
    if sys.stdout is not None:
        print("Birdtracks standalone runtime is ready.")
    return 0


def main(arguments: list[str] | None = None) -> int:
    """Dispatch the standalone application or its private kernel process."""
    args = list(sys.argv[1:] if arguments is None else arguments)
    if args and args[0] == _KERNEL_ARGUMENT:
        return _run_kernel(args[1:])
    if args == ["--version"]:
        from importlib.metadata import version

        print(version("birdtracks"))
        return 0
    if args == ["--self-test"]:
        return _self_test()
    if args:
        raise SystemExit(f"unknown Birdtracks argument: {args[0]}")
    return _run_application()


if __name__ == "__main__":
    raise SystemExit(main())
