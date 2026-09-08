"""Permutation computation backends."""

from .cython import cython_available, cython_backend
from .protocol import PermutationBackend
from .python import PythonBackend, python_backend

__all__ = [
    "PermutationBackend",
    "PythonBackend",
    "cython_available",
    "cython_backend",
    "python_backend",
]
