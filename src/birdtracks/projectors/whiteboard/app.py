"""Desktop launcher for the standalone whiteboard."""

from __future__ import annotations

from importlib.util import find_spec
import os
from os import PathLike
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen


def _free_port() -> int:
    """Reserve an ephemeral localhost port for the private Voilà server."""

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_server(process: subprocess.Popen[bytes], url: str) -> None:
    """Wait until Voilà serves the whiteboard or report an early exit."""

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("the whiteboard server exited before it was ready")
        try:
            with urlopen(url, timeout=0.5):
                return
        except (OSError, URLError):
            time.sleep(0.05)
    raise TimeoutError("the whiteboard server did not start within 30 seconds")


def _stop_server(process: subprocess.Popen[bytes]) -> None:
    """Stop the private Voilà child after the desktop window closes."""

    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _webview_gui() -> str | None:
    """Use the pip-installable Qt backend on Linux desktop sessions."""

    return "qt" if sys.platform.startswith("linux") else None


def _application_entry() -> Path:
    """Locate the bundled Voilà entry document."""

    packaged_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parents[2]))
    candidates = (
        packaged_root / "birdtracks" / "projectors" / "whiteboard_app.py",
        Path(__file__).resolve().parent.parent / "whiteboard_app.py",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("the bundled whiteboard entry is missing")


def _asset_path(name: str) -> Path:
    """Locate a packaged whiteboard asset for installer integration."""

    packaged_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parents[2]))
    candidates = (
        packaged_root / "birdtracks" / "projectors" / "static" / name,
        Path(__file__).resolve().parent.parent / "static" / name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"the bundled whiteboard asset is missing: {name}")


def _write_if_changed(path: Path, content: str | bytes) -> bool:
    """Write desktop integration data only when its contents changed."""

    encoded = content.encode("utf-8") if isinstance(content, str) else content
    if path.exists() and path.read_bytes() == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return True


def _desktop_launcher() -> str:
    """Return an executable command suitable for a desktop ``Exec`` entry."""

    if getattr(sys, "frozen", False):
        parts = [sys.executable]
    else:
        invoked = Path(sys.argv[0])
        if invoked.name.startswith("birdtracks-whiteboard") and invoked.exists():
            parts = [str(invoked.resolve())]
        else:
            installed = shutil.which("birdtracks-whiteboard")
            parts = (
                [installed]
                if installed is not None
                else [sys.executable, "-m", "birdtracks.projectors.whiteboard.app"]
            )
    return " ".join(f'"{part.replace(chr(34), chr(92) + chr(34))}"' for part in parts)


def _ensure_linux_desktop_integration() -> None:
    """Register the active launcher and file icon for ``.whiteboard`` files."""

    if not sys.platform.startswith("linux"):
        return
    data_root = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    applications = data_root / "applications"
    mime_root = data_root / "mime"
    icon_root = data_root / "icons" / "hicolor" / "scalable"
    desktop = "\n".join((
        "[Desktop Entry]",
        "Type=Application",
        "Name=Birdtracks Whiteboard",
        "Comment=Exact birdtrack projector whiteboard",
        f"Exec={_desktop_launcher()} %f",
        "Icon=birdtracks-whiteboard-projector",
        "Terminal=false",
        "Categories=Education;Science;",
        "MimeType=application/x-birdtracks-whiteboard;",
        "StartupWMClass=Birdtracks Whiteboard",
        "",
    ))
    mime = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-birdtracks-whiteboard">
    <comment>Birdtracks whiteboard</comment>
    <glob pattern="*.whiteboard"/>
    <icon name="birdtracks-whiteboard-file-projector"/>
  </mime-type>
</mime-info>
"""
    changed = _write_if_changed(
        applications / "birdtracks-whiteboard.desktop", desktop
    )
    changed |= _write_if_changed(
        mime_root / "packages" / "birdtracks-whiteboard.xml", mime
    )
    changed |= _write_if_changed(
        icon_root / "apps" / "birdtracks-whiteboard-projector.svg",
        _asset_path("birdtracks-whiteboard-file.svg").read_bytes(),
    )
    changed |= _write_if_changed(
        icon_root / "mimetypes" / "birdtracks-whiteboard-file-projector.svg",
        _asset_path("birdtracks-whiteboard-file.svg").read_bytes(),
    )
    if changed:
        for command in (
            ["update-mime-database", str(mime_root)],
            ["update-desktop-database", str(applications)],
        ):
            if shutil.which(command[0]) is not None:
                subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    if shutil.which("xdg-mime") is not None:
        subprocess.run(
            [
                "xdg-mime", "default", "birdtracks-whiteboard.desktop",
                "application/x-birdtracks-whiteboard",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _run_kernel(arguments: list[str]) -> int:
    """Run the bundled Python kernel for a frozen whiteboard executable."""

    from ..standalone import _run_kernel as run_kernel

    return run_kernel(arguments)


def _run_frozen_server(arguments: list[str]) -> int:
    """Run Voilà inside a frozen child process."""

    from tempfile import TemporaryDirectory

    from ..standalone import _write_runtime_kernelspec

    try:
        from voila.app import Voila
    except ImportError as exc:
        raise ImportError(
            "the whiteboard application requires the birdtracks app dependencies"
        ) from exc

    if len(arguments) != 1:
        raise SystemExit("the frozen whiteboard server requires a port")
    with TemporaryDirectory(prefix="birdtracks-whiteboard-") as temporary:
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
                "--Voila.open_browser=False",
                "--Voila.ip=127.0.0.1",
                f"--Voila.port={arguments[0]}",
                "--Application.log_level=CRITICAL",
            ]
        )
    return 0


def launch_whiteboard_app(
    session: str | PathLike[str] | None = None,
    *,
    debug: bool = False,
) -> int:
    """Run the standalone whiteboard in its own native webview window."""

    if find_spec("voila") is None:
        raise ImportError(
            "the whiteboard application requires: pip install 'birdtracks[app]'"
        )
    if find_spec("webview") is None:
        raise ImportError(
            "the desktop whiteboard requires: pip install 'birdtracks[app]'"
        )

    _ensure_linux_desktop_integration()

    entry = Path(__file__).resolve().parent.parent / "whiteboard_app.py"
    environment = os.environ.copy()
    environment["BIRDTRACKS_EXPRESSION_ROOT"] = str(Path.cwd())
    environment["BIRDTRACKS_DEBUG"] = "1" if debug else "0"
    if session is None:
        environment.pop("BIRDTRACKS_WHITEBOARD_SESSION", None)
    else:
        environment["BIRDTRACKS_WHITEBOARD_SESSION"] = str(session)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--birdtracks-whiteboard-server", str(port)]
    else:
        command = [
            sys.executable,
            "-m",
            "voila",
            str(entry),
            "--VoilaConfiguration.extension_language_mapping=.py=python",
            "--VoilaConfiguration.language_kernel_mapping=python=python3",
            "--Voila.open_browser=False",
            "--Voila.ip=127.0.0.1",
            f"--Voila.port={port}",
            "--Application.log_level=CRITICAL",
        ]
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        import webview

        window = webview.create_window(
            "Birdtracks Whiteboard",
            html=(
                "<html><body style='font-family:sans-serif;padding:2rem'>"
                "Starting Birdtracks Whiteboard…</body></html>"
            ),
            width=1400,
            height=900,
            min_size=(900, 600),
        )

        def load_server() -> None:
            _wait_for_server(process, url)
            window.load_url(url)

        def start_server_waiter() -> None:
            threading.Thread(target=load_server, daemon=True).start()

        webview.start(func=start_server_waiter, gui=_webview_gui(), debug=debug)
        return 0
    finally:
        _stop_server(process)


def main(arguments: list[str] | None = None) -> int:
    """Launch a new whiteboard or open a named ``.whiteboard`` document."""

    args = list(sys.argv[1:] if arguments is None else arguments)
    if args and args[0] == "--birdtracks-kernel":
        return _run_kernel(args[1:])
    if args and args[0] == "--birdtracks-whiteboard-server":
        return _run_frozen_server(args[1:])
    if args and args[0] == "--asset-path":
        if len(args) != 2:
            raise SystemExit("--asset-path requires an asset name")
        print(_asset_path(args[1]))
        return 0

    import argparse

    parser = argparse.ArgumentParser(prog="birdtracks-whiteboard")
    parser.add_argument("session", nargs="?", help="document path or expression name")
    parser.add_argument("--debug", action="store_true")
    options = parser.parse_args(args)
    return launch_whiteboard_app(options.session, debug=options.debug)


__all__ = ["launch_whiteboard_app", "main"]
