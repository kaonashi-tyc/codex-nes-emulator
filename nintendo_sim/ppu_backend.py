from __future__ import annotations

import importlib.util
import importlib.machinery
import os
import site
import sys
import sysconfig
from pathlib import Path
from typing import Type

from .ppu import PPU as PythonPPU

VALID_BACKENDS = ("auto", "python", "cython")


def _iter_candidate_package_dirs() -> list[Path]:
    dirs: list[Path] = []
    seen: set[Path] = set()

    def _add(path_str: str | None) -> None:
        if not path_str:
            return
        path = Path(path_str).resolve()
        if path in seen:
            return
        seen.add(path)
        dirs.append(path)

    paths = sysconfig.get_paths()
    _add(paths.get("platlib"))
    _add(paths.get("purelib"))

    try:
        for path_str in site.getsitepackages():
            _add(path_str)
    except Exception:
        pass

    try:
        _add(site.getusersitepackages())
    except Exception:
        pass

    project_root = Path(__file__).resolve().parents[1]
    for build_lib in sorted(project_root.glob("build/lib.*")):
        _add(str(build_lib))

    return dirs


def _load_external_cython_ppu() -> Type[PythonPPU] | None:
    for root in _iter_candidate_package_dirs():
        package_dir = root / "nintendo_sim"
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            candidate = package_dir / f"ppu_cython{suffix}"
            if not candidate.exists():
                continue
            spec = importlib.util.spec_from_file_location("nintendo_sim.ppu_cython", candidate)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules["nintendo_sim.ppu_cython"] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop("nintendo_sim.ppu_cython", None)
                continue
            ppu_cls = getattr(module, "PPU", None)
            if ppu_cls is not None:
                return ppu_cls
    return None


def resolve_ppu_class(preferred: str | None) -> tuple[Type[PythonPPU], str]:
    mode = (preferred or os.getenv("NES_PPU_BACKEND", "auto")).strip().lower()
    if mode not in VALID_BACKENDS:
        raise ValueError(f"Unknown PPU backend '{mode}'. Expected one of: {', '.join(VALID_BACKENDS)}")

    if mode in ("auto", "cython"):
        try:
            from .ppu_cython import PPU as CythonPPU
        except Exception as exc:
            fallback_cls = _load_external_cython_ppu()
            if fallback_cls is not None:
                return fallback_cls, "cython"
            if mode == "cython":
                raise RuntimeError(
                    "Cython PPU backend requested but not available. "
                    "Build/install it first with: python -m pip install ."
                ) from exc
        else:
            return CythonPPU, "cython"

    return PythonPPU, "python"
