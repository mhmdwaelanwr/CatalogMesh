"""Guided configuration facade with stable v3.1 filesystem behavior."""

from __future__ import annotations

from pathlib import Path

from .paths import runtime_root
from . import _setup_impl as _impl

_ROOT = runtime_root()
_impl.ROOT = _ROOT
_impl.ENV_FILE = _ROOT / ".env"
_impl.MAIN_SCRIPT = _ROOT / "product_sorter.py"

if not hasattr(_impl, "_ORIGINAL_BUILD_ENV_TEXT"):
    _impl._ORIGINAL_BUILD_ENV_TEXT = _impl.build_env_text
if not hasattr(_impl, "_ORIGINAL_SAVE_ENV"):
    _impl._ORIGINAL_SAVE_ENV = _impl.save_env

_DESKTOP_ENV_KEYS = (
    "APP_THEME",
    "PRODUCT_SORTER_MD_REPORT",
    "BENCHMARK_LIMIT",
    "PRODUCT_SORTER_OUTPUT_MODE",
)


def _build_env_text(values: dict[str, str]) -> str:
    """Keep the stable setup schema while persisting desktop-only settings."""
    text = _impl._ORIGINAL_BUILD_ENV_TEXT(values).rstrip()
    existing = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    extras = [name for name in _DESKTOP_ENV_KEYS if name not in existing]
    if extras:
        text += "\n\n# Desktop application settings\n"
        text += "\n".join(
            f"{name}={_impl.clean(str(values.get(name, '')))}" for name in extras
        )
    return text + "\n"


def _save_env(values: dict[str, str], path: Path | None = None) -> None:
    _impl._ORIGINAL_SAVE_ENV(values, _impl.ENV_FILE if path is None else path)


_impl.build_env_text = _build_env_text
_impl.save_env = _save_env

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
