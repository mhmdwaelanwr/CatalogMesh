"""Central filesystem locations for source, installed, and frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def _source_root() -> Path | None:
    candidate = PACKAGE_DIR.parent.parent
    if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "ai_product_photo_sorter").is_dir():
        return candidate
    return None


def runtime_root() -> Path:
    """Return the compatibility root used by configuration and launchers."""
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


def env_file() -> Path:
    return runtime_root() / ".env"


def requirements_file() -> Path:
    legacy = runtime_root() / "requirements.txt"
    return legacy if legacy.is_file() else PACKAGE_DIR / "requirements.txt"
