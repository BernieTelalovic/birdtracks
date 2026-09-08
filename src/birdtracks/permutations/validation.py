"""Validation helpers for public permutation inputs."""

from collections.abc import Iterable, Mapping


def require_label(value: object) -> int:
    """Validate an integer label without narrowing its precision."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"permutation labels must be integers, got {value!r}")
    return value


def validated_mapping(
    mapping: Mapping[int, int] | Iterable[tuple[int, int]],
) -> dict[int, int]:
    """Validate a finite-support bijection and remove fixed points."""
    try:
        raw = dict(mapping)
    except (TypeError, ValueError) as exc:
        raise TypeError("expected a mapping or iterable of (source, target) pairs") from exc
    checked = {
        require_label(source): require_label(target)
        for source, target in raw.items()
    }
    result = {source: target for source, target in checked.items() if source != target}
    if set(result) != set(result.values()):
        raise ValueError("a permutation must bijectively map its support onto itself")
    return result
