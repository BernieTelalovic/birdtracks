"""Global settings for birdtrack computations."""

from __future__ import annotations


# Named algebraic identities that simplification operations may apply.
# Keep every rule enabled by default; callers may disable individual rules
# for an entire process by setting the corresponding value to ``False``.
SIMPLIFICATION_RULES: dict[str, bool] = {
    "multiply_connected_symmetriser_antisymmetriser_annihilation": True,
    "mismatched_young_layers_annihilation": True,
    "same_type_nested_absorption": True,
    "symmetriser_recursion": True,
    "antisymmetriser_recursion": True,
    "permutation_left_symmetriser_absorption": True,
    "permutation_right_symmetriser_absorption": True,
    "permutation_left_antisymmetriser_absorption": True,
    "permutation_right_antisymmetriser_absorption": True,
}


def simplification_rule_enabled(name: str) -> bool:
    """Return whether a named identity may be used for simplification."""
    return SIMPLIFICATION_RULES.get(name, True)


__all__ = ["SIMPLIFICATION_RULES", "simplification_rule_enabled"]
