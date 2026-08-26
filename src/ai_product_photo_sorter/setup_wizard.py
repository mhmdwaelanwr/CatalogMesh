"""Guided configuration facade with stable v3.1 filesystem behavior."""

from __future__ import annotations

from pathlib import Path

from .paths import runtime_root
from . import _setup_impl as _impl

_ROOT = runtime_root()
_impl.ROOT = _ROOT
_impl.ENV_FILE = _ROOT / ".env"
_impl.MAIN_SCRIPT = _ROOT / "product_sorter.py"

if not hasattr(_impl, "_ORIGINAL_SAVE_ENV"):
    _impl._ORIGINAL_SAVE_ENV = _impl.save_env


def _save_env(values: dict[str, str], path: Path | None = None) -> None:
    _impl._ORIGINAL_SAVE_ENV(values, _impl.ENV_FILE if path is None else path)


_impl.save_env = _save_env

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
