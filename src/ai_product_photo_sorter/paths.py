"""Central filesystem locations for source, installed, and frozen builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
_APP_DIR_NAME = "CatalogMesh"


def _source_root() -> Path | None:
    candidate = PACKAGE_DIR.parent.parent
    if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "ai_product_photo_sorter").is_dir():
        return candidate
    return None


def runtime_root() -> Path:
    """Return the compatibility/resource root used by launchers and bundled assets.

    Frozen PyInstaller applications must keep resolving packaged resources from
    ``sys._MEIPASS``. User configuration is intentionally handled separately by
    :func:`env_file` so it never points at PyInstaller's temporary extraction
    directory.
    """
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            return Path(bundle).resolve()
        return Path(sys.executable).resolve().parent
    source = _source_root()
    if source is not None:
        return source
    # Installed wheels keep the legacy top-level compatibility modules beside
    # the package in site-packages, matching the v3.1 runtime layout.
    return PACKAGE_DIR.parent


def _frozen_config_root() -> Path:
    """Return a stable per-user configuration directory for frozen builds.

    An existing ``.env`` beside the executable opts into portable mode. This is
    intentionally existence-gated: CatalogMesh never creates credentials beside
    the executable unless the user has already chosen that layout.
    """
    executable_root = Path(sys.executable).resolve().parent
    portable = executable_root / ".env"
    if portable.is_file():
        return executable_root

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base).expanduser().resolve() / _APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / _APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config).expanduser().resolve() / _APP_DIR_NAME
    return Path.home() / ".config" / _APP_DIR_NAME


def env_file() -> Path:
    """Return the CatalogMesh environment file without using a temp bundle path."""
    if getattr(sys, "frozen", False):
        return _frozen_config_root() / ".env"
    return runtime_root() / ".env"


def requirements_file() -> Path:
    legacy = runtime_root() / "requirements.txt"
    return legacy if legacy.is_file() else PACKAGE_DIR / "requirements.txt"
