"""Finite-support permutations of arbitrary-size integer labels."""

from .batch import multiply_many
from .operations import compose
from .rendering import (
    cycle_notation,
    get_display_notation,
    latex,
    set_display_notation,
)
from .types import Permutation

__all__ = [
    "Permutation",
    "compose",
    "cycle_notation",
    "get_display_notation",
    "latex",
    "multiply_many",
    "set_display_notation",
]
