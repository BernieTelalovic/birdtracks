"""Optional access to standalone representation tensor-product decomposition.

Values and results belong to pair_multiplication; no projector mapping is implied.
"""

from importlib import import_module
from types import ModuleType
from typing import Any


def pair_backend() -> ModuleType:
    """Load pair_multiplication on demand, including its compiled extension.

    Use the returned module's Pair, YoungDiagram, NullDiagram and DirectSum
    constructors. Their native constructor and metadata semantics are preserved.
    """
    try:
        return import_module("pair_multiplication")
    except ImportError as exc:
        raise ImportError(
            "Representation products require the standalone pair_multiplication "
            "package and its compiled extension in this Python environment. "
            "Install it with: python -m pip install -e /path/to/pair_multiplication. "
            f"Original import error: {exc}"
        ) from exc


def tensor_product(left: Any, right: Any, *, Nc: int | None = None) -> Any:
    """Multiply native representation values, optionally evaluating the result.

    Pair partitions are (barred, unbarred). With Nc=None, multiplication retains
    the operands' existing semantics; a supplied Nc evaluates the product via
    evaluate_for_Nc. Zero and trivial representations remain distinct native
    values. This operation does not compose birdtrack projection operators.
    """
    backend = pair_backend()
    supported = (backend.NullDiagram, backend.DirectSum)
    if not isinstance(left, supported) or not isinstance(right, supported):
        raise TypeError("Operands must be pair_multiplication representation values")
    result = left * right
    return result if Nc is None else result.evaluate_for_Nc(Nc)
