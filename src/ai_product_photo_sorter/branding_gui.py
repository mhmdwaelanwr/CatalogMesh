"""Desktop display-brand adapter for the v3.x compatibility application."""
from __future__ import annotations

from typing import Any

from .branding import APP_NAME, APP_NAME_UPPER, APP_TAGLINE, LEGACY_DISPLAY_NAME


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = ()
    for child in children:
        yield from _walk(child)


def apply_branding_gui(module: Any) -> None:
    """Apply CatalogMesh as the visible brand without renaming v3.x APIs."""
    for language, catalog in module.L.items():
        catalog["title"] = APP_NAME
        catalog["subtitle"] = APP_TAGLINE.get(language, APP_TAGLINE["en"])

    base_build = module.App.build
    base_apply_language = module.App.apply_language

    def build(self):
        base_build(self)
        for widget in _walk(self.root):
            try:
                text = widget.cget("text")
            except Exception:
                continue
            if text == "AI PRODUCT PHOTO SORTER":
                widget.configure(text=APP_NAME_UPPER)
            elif text == LEGACY_DISPLAY_NAME:
                widget.configure(text=APP_NAME)

    def apply_language(self):
        base_apply_language(self)
        # The native title bar should receive logical text. Arabic shaping is
        # handled only for Tk-rendered widgets by gui_workflow/global i18n.
        self.root.title(APP_NAME)

    module.App.build = build
    module.App.apply_language = apply_language
    module.APP_DISPLAY_NAME = APP_NAME
