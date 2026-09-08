"""Optional Cython extension configuration.

Normal isolated builds do not require Cython and retain the Python backend.
Development builds with Cython already installed compile the optional backend.
"""

from setuptools import Extension, setup

try:
    from Cython.Build import cythonize
except ImportError:
    extensions = []
else:
    extensions = cythonize(
        [
            Extension(
                "birdtracks.permutations.backends._cython",
                ["src/birdtracks/permutations/backends/_cython.pyx"],
            )
        ],
        build_dir="build/cython",
        compiler_directives={
            "boundscheck": False,
            "language_level": "3",
            "wraparound": False,
        },
    )

setup(ext_modules=extensions)
