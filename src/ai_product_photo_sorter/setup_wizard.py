"""Guided configuration facade with stable v3.1 filesystem behavior."""

from __future__ import annotations

from pathlib import Path

from .paths import runtime_root
from . import _setup_impl as _impl
from .ollama_local import (
    DEFAULT_BASE_URL,
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    discover_ollama_models,
)

_ROOT = runtime_root()
_impl.ROOT = _ROOT
_impl.ENV_FILE = _ROOT / ".env"
_impl.MAIN_SCRIPT = _ROOT / "product_sorter.py"

if not hasattr(_impl, "_ORIGINAL_BUILD_ENV_TEXT"):
    _impl._ORIGINAL_BUILD_ENV_TEXT = _impl.build_env_text
if not hasattr(_impl, "_ORIGINAL_SAVE_ENV"):
    _impl._ORIGINAL_SAVE_ENV = _impl.save_env
if not hasattr(_impl, "_ORIGINAL_COLLECT_SETTINGS"):
    _impl._ORIGINAL_COLLECT_SETTINGS = _impl.collect_settings

_DESKTOP_ENV_KEYS = (
    "APP_THEME",
    "PRODUCT_SORTER_MD_REPORT",
    "BENCHMARK_LIMIT",
    "PRODUCT_SORTER_OUTPUT_MODE",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_TIMEOUT",
    "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES",
)


def _build_env_text(values: dict[str, str]) -> str:
    """Keep the stable setup schema while persisting desktop/local settings."""
    text = _impl._ORIGINAL_BUILD_ENV_TEXT(values).rstrip()
    existing = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    extras = [name for name in _DESKTOP_ENV_KEYS if name not in existing]
    if extras:
        text += "\n\n# Desktop and local-AI settings\n"
        text += "\n".join(
            f"{name}={_impl.clean(str(values.get(name, '')))}" for name in extras
        )
    return text + "\n"


def _save_env(values: dict[str, str], path: Path | None = None) -> None:
    _impl._ORIGINAL_SAVE_ENV(values, _impl.ENV_FILE if path is None else path)


def _collect_settings(current: dict[str, str]) -> dict[str, str]:
    values = _impl._ORIGINAL_COLLECT_SETTINGS(current)
    selected = {item.strip().lower() for item in values.get("AI_PROVIDERS", "").split(",")}
    if "ollama" not in selected and "local" not in selected:
        return values

    print("\nOLLAMA local vision settings:")
    values["OLLAMA_BASE_URL"] = _impl.ask_text(
        "Ollama server URL",
        current.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
        True,
    )
    try:
        models = discover_ollama_models(values["OLLAMA_BASE_URL"], vision_only=True)
    except Exception as exc:
        models = []
        print(f"Could not discover local Ollama vision models: {exc}")
    if models:
        current_model = current.get("OLLAMA_MODEL", DEFAULT_MODEL)
        values["OLLAMA_MODEL"] = _impl.choose_from_list("ollama", current_model, models)
    else:
        values["OLLAMA_MODEL"] = _impl.ask_text(
            "Ollama vision model",
            current.get("OLLAMA_MODEL", DEFAULT_MODEL),
            True,
        )
    values["OLLAMA_KEEP_ALIVE"] = _impl.ask_text(
        "Keep Ollama model loaded (for example 10m)",
        current.get("OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE),
        True,
    )
    values["OLLAMA_TIMEOUT"] = _impl.ask_number(
        "Ollama inference timeout in seconds",
        current.get("OLLAMA_TIMEOUT", str(DEFAULT_TIMEOUT)),
        5,
        3600,
        True,
    )
    values["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"] = _impl.ask_number(
        "Encoded image cache entries",
        current.get("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES", "24"),
        0,
        256,
        True,
    )
    return values


_impl.build_env_text = _build_env_text
_impl.save_env = _save_env
_impl.collect_settings = _collect_settings

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main