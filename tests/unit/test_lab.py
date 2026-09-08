"""Tests for the Birdtracks JupyterLab launcher."""

import sys
from types import ModuleType

from birdtracks import lab


def test_lab_opens_current_directory(monkeypatch, tmp_path) -> None:
    calls = []

    class FakeLabApp:
        @staticmethod
        def launch_instance(argv) -> None:
            calls.append(argv)

    jupyterlab = ModuleType("jupyterlab")
    labapp = ModuleType("jupyterlab.labapp")
    labapp.LabApp = FakeLabApp
    monkeypatch.setitem(sys.modules, "jupyterlab", jupyterlab)
    monkeypatch.setitem(sys.modules, "jupyterlab.labapp", labapp)
    monkeypatch.chdir(tmp_path)

    assert lab.main() == 0
    assert calls == [
        [
            f"--ServerApp.root_dir={tmp_path}",
            "--ServerApp.open_browser=True",
        ]
    ]
