from __future__ import annotations

from setuptools import Extension, setup

try:
    from Cython.Build import cythonize
except ImportError as exc:
    raise SystemExit(
        "Cython is required to build the optimized PPU backend. "
        "Install it first: pip install cython"
    ) from exc


extensions = [
    Extension(
        "nintendo_sim.ppu_cython",
        ["nintendo_sim/ppu_cython.pyx"],
    )
]

setup(
    ext_modules=cythonize(
        extensions,
        build_dir="build/cython",
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "initializedcheck": False,
        },
    ),
)
