from pathlib import Path

import pytest

from birdtracks.clean import clean


def _repository(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "birdtracks"\n', encoding="utf-8"
    )
    (tmp_path / "src" / "birdtracks").mkdir(parents=True)
    return tmp_path


def test_clean_removes_generated_files_but_preserves_documents(tmp_path) -> None:
    root = _repository(tmp_path)
    generated = [
        root / "build" / "artifact.o",
        root / ".pytest_cache" / "state",
        root / "src" / "birdtracks.egg-info" / "PKG-INFO",
        root / "src" / "birdtracks" / "__pycache__" / "module.pyc",
        root / "src" / "birdtracks" / "backend.so",
    ]
    for path in generated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated", encoding="utf-8")
    document = root / "expressions" / "notes.whiteboard"
    document.parent.mkdir()
    document.write_text("saved", encoding="utf-8")

    removed = clean(root)

    assert removed
    assert all(not path.exists() for path in generated)
    assert document.read_text(encoding="utf-8") == "saved"


def test_clean_dry_run_does_not_delete_targets(tmp_path) -> None:
    root = _repository(tmp_path)
    artifact = root / "dist" / "birdtracks.whl"
    artifact.parent.mkdir()
    artifact.write_text("generated", encoding="utf-8")

    assert root / "dist" in clean(root, dry_run=True)
    assert artifact.exists()


def test_clean_refuses_non_repository_directory(tmp_path) -> None:
    with pytest.raises(ValueError, match="repository root"):
        clean(tmp_path)
