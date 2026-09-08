"""Load the flat YAML configuration for projector diagram aesthetics."""

from __future__ import annotations

from os import PathLike
from pathlib import Path

_DEFAULT_PATH = Path(__file__).with_name("projector-widget.yaml")

_NUMERIC_KEYS = {
    "operator_width",
    "level_spacing",
    "step",
    "operator_padding_fraction",
    "top_margin",
    "coefficient_space",
    "line_width",
    "operator_line_width",
    "handle_radius",
    "handle_line_width",
    "coefficient_font_size",
    "fraction_font_size",
    "fraction_height",
    "fraction_bar_width",
    "fraction_line_width",
}
_COLOR_KEYS = {
    "background_color",
    "border_color",
    "line_color",
    "symmetriser_color",
    "antisymmetriser_color",
    "port_handle_color",
    "free_line_handle_color",
}


def load_projector_style(
    path: str | PathLike[str] | None = None,
) -> dict[str, float | str]:
    """Load and validate a flat ``key: value`` YAML style file.

    The deliberately flat schema needs no runtime YAML dependency. Quoted and
    unquoted scalar values and comments are supported.
    """
    source = _DEFAULT_PATH if path is None else Path(path)
    values = _parse_flat_yaml(source.read_text(encoding="utf-8"))
    expected = _NUMERIC_KEYS | _COLOR_KEYS
    missing = expected - values.keys()
    unknown = values.keys() - expected
    if missing:
        raise ValueError(f"projector style is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"unknown projector style settings: {', '.join(sorted(unknown))}")

    result: dict[str, float | str] = {}
    for key in _NUMERIC_KEYS:
        try:
            number = float(values[key])
        except ValueError as exc:
            raise ValueError(f"projector style {key} must be numeric") from exc
        if number <= 0:
            raise ValueError(f"projector style {key} must be positive")
        result[key] = number
    if result["operator_width"] != 1.0:
        raise ValueError("projector style operator_width must be exactly 1")
    if result["operator_padding_fraction"] >= 0.5:
        raise ValueError(
            "projector style operator_padding_fraction must be less than 0.5"
        )
    for key in _COLOR_KEYS:
        result[key] = values[key]
    return result


def _parse_flat_yaml(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid projector YAML on line {line_number}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key or not value:
            raise ValueError(f"invalid projector YAML on line {line_number}")
        if key in result:
            raise ValueError(f"duplicate projector style setting {key!r}")
        if value[:1] in {'"', "'"}:
            if value[-1:] != value[0]:
                raise ValueError(f"unterminated YAML string on line {line_number}")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        result[key] = value
    return result


__all__ = ["load_projector_style"]
