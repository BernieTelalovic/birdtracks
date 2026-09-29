"""Remove local Birdtracks build products without touching user documents."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
import shutil


_CACHE_DIRECTORIES = (
    "build",
    "dist",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)
_SOURCE_ROOTS = ("src", "tests", "scripts", "benchmarks", "packaging", "examples")
_COMPILED_SUFFIXES = (".so", ".pyd", ".dll", ".dylib")


def _repository_root(start: Path) -> Path:
    root = start.resolve()
    pyproject = root / "pyproject.toml"
    package = root / "src" / "birdtracks"
    if not pyproject.is_file() or not package.is_dir():
        raise ValueError("run birdtracks-clean from the Birdtracks repository root")
    if 'name = "birdtracks"' not in pyproject.read_text(encoding="utf-8"):
        raise ValueError("the current directory is not the Birdtracks repository root")
    return root


def _targets(root: Path) -> tuple[Path, ...]:
    targets = [root / name for name in _CACHE_DIRECTORIES]
    targets.extend((root / "src").glob("*.egg-info"))
    for relative in _SOURCE_ROOTS:
        source_root = root / relative
        if not source_root.is_dir():
            continue
        targets.extend(source_root.rglob("__pycache__"))
        targets.extend(source_root.rglob("*.pyc"))
    package = root / "src" / "birdtracks"
    for suffix in _COMPILED_SUFFIXES:
        targets.extend(package.rglob(f"*{suffix}"))
    result: list[Path] = []
    for target in sorted(set(targets), key=lambda path: (len(path.parts), str(path))):
        if any(parent.is_dir() and parent in target.parents for parent in result):
            continue
        result.append(target)
    return tuple(result)


def clean(root: Path, *, dry_run: bool = False) -> tuple[Path, ...]:
    """Remove known generated files below a validated repository root."""
    removed: list[Path] = []
    for target in _targets(_repository_root(root)):
        if not target.exists() and not target.is_symlink():
            continue
        removed.append(target)
        if dry_run:
            continue
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    return tuple(removed)


def _display(paths: Iterable[Path], root: Path) -> None:
    for path in paths:
        print(path.relative_to(root.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="clear Birdtracks caches, build products, and compiled extensions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list targets without deleting them",
    )
    args = parser.parse_args()
    root = Path.cwd()
    try:
        removed = clean(root, dry_run=args.dry_run)
    except ValueError as error:
        parser.error(str(error))
    _display(removed, root)
    action = "Would remove" if args.dry_run else "Removed"
    print(f"{action} {len(removed)} generated path(s).")
    if not args.dry_run:
        print("Restart any running Birdtracks kernel or app before retesting.")


if __name__ == "__main__":
    main()
