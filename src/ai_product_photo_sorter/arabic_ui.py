"""Arabic display helpers for Tk/ttk renderers with incomplete BiDi support."""
from __future__ import annotations

import os
import re
import sys
from typing import Any

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover - package dependencies normally provide these.
    arabic_reshaper = None
    get_display = None


_ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
_FORMAT_FIELD_RE = re.compile(r"\{[^{}]+\}")
_PREPARED_CATALOG_IDS: set[int] = set()


def contains_arabic(value: object) -> bool:
    """Return whether *value* contains Arabic-script code points."""
    return bool(_ARABIC_RE.search(str(value or "")))


def arabic_visual_fix_enabled(
    *,
    platform: str | None = None,
    env_value: str | None = None,
) -> bool:
    """Return whether Tk should receive pre-shaped visual-order Arabic text.

    Tk on Linux commonly lacks the full complex-text/BiDi path used by native
    desktop controls. Windows/macOS are left native by default, while the
    environment variable allows an explicit override for unusual Tk builds.
    """
    if env_value is None:
        env_value = os.environ.get("PRODUCT_SORTER_ARABIC_SHAPING")
    if env_value is not None:
        normalized = str(env_value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "force"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    current_platform = sys.platform if platform is None else platform
    return str(current_platform).startswith("linux")


def _mask_format_fields(line: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = f"PSFMTFIELD{len(placeholders)}X"
        placeholders[token] = match.group(0)
        return token

    return _FORMAT_FIELD_RE.sub(replace, line), placeholders


def shape_arabic_for_tk(text: object, *, force: bool | None = None) -> str:
    """Shape Arabic and resolve BiDi into visual order for Tk display widgets."""
    value = "" if text is None else str(text)
    enabled = arabic_visual_fix_enabled() if force is None else bool(force)
    if not enabled or not contains_arabic(value):
        return value
    rendered: list[str] = []
    if arabic_reshaper is None or get_display is None:
        # Dependency-free fallback for unusual/offline installations.  Keep
        # ASCII/format tokens internally LTR while reversing the surrounding
        # Arabic visual sequence for Tk renderers that lack BiDi.  Normal
        # installations use arabic-reshaper + python-bidi below for joined
        # presentation forms and full Unicode BiDi behavior.
        token_re = re.compile(r"([A-Za-z0-9_.:/+@-]+|\{[^{}]+\})")
        for line in value.split("\n"):
            if not contains_arabic(line):
                rendered.append(line); continue
            parts = token_re.split(line)
            visual = []
            for part in reversed(parts):
                if not part:
                    continue
                if token_re.fullmatch(part):
                    visual.append(part)
                else:
                    visual.append(part[::-1])
            rendered.append("".join(visual))
        return "\n".join(rendered)

    # Resolve line-by-line so wrapped help/status strings keep their explicit
    # newline structure rather than letting one paragraph affect the next.
    for line in value.split("\n"):
        if not contains_arabic(line):
            rendered.append(line)
            continue
        masked, placeholders = _mask_format_fields(line)
        reshaped = arabic_reshaper.reshape(masked)
        display = get_display(reshaped, base_dir="R")
        for token, original in placeholders.items():
            display = display.replace(token, original)
        rendered.append(display)
    return "\n".join(rendered)


def _shape_value(value: Any, *, force: bool) -> Any:
    if isinstance(value, str):
        return shape_arabic_for_tk(value, force=force)
    if isinstance(value, tuple):
        return tuple(_shape_value(item, force=force) for item in value)
    if isinstance(value, list):
        return [_shape_value(item, force=force) for item in value]
    if isinstance(value, dict):
        return {key: _shape_value(item, force=force) for key, item in value.items()}
    return value


def prepare_arabic_catalog(catalog: Any, *, force: bool | None = None) -> bool:
    """Pre-shape the Arabic branch of a mutable translation catalog once."""
    if not isinstance(catalog, dict) or "ar" not in catalog:
        return False
    enabled = arabic_visual_fix_enabled() if force is None else bool(force)
    if not enabled:
        return False
    identity = id(catalog)
    if identity in _PREPARED_CATALOG_IDS:
        return True
    catalog["ar"] = _shape_value(catalog["ar"], force=True)
    _PREPARED_CATALOG_IDS.add(identity)
    return True


def prepare_loaded_gui_catalogs(
    package_prefix: str = "ai_product_photo_sorter",
    *,
    force: bool | None = None,
) -> int:
    """Prepare Arabic dictionaries already loaded by the desktop GUI facade."""
    enabled = arabic_visual_fix_enabled() if force is None else bool(force)
    if not enabled:
        return 0

    prepared = 0
    for name, loaded in tuple(sys.modules.items()):
        if loaded is None or not name.startswith(package_prefix):
            continue
        leaf = name.rsplit(".", 1)[-1]
        if "gui" not in leaf and leaf != "_gui_impl":
            continue
        for attr in ("_TEXT", "_REPORT_TEXT"):
            catalog = getattr(loaded, attr, None)
            if prepare_arabic_catalog(catalog, force=True):
                prepared += 1
    return prepared
