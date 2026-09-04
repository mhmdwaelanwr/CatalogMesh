"""Canonical runtime labels for the CatalogMesh workflow workspaces."""
from __future__ import annotations

from typing import Any

from .gui_icons import apply_gui_icons
from .gui_workflow import WORKSPACE_USAGE_ORDER


def apply_workspace_i18n(module: Any) -> None:
    """Keep all 12 workspace names on the global EN/AR/ZH translation path."""
    base_apply_language = module.App.apply_language

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "main_tabs") or not hasattr(self, "ui_translate"):
            return
        tabs = tuple(self.main_tabs.tabs())
        for tab_id, english_label in zip(tabs, WORKSPACE_USAGE_ORDER):
            try:
                self.main_tabs.tab(tab_id, text=self.ui_translate(english_label))
            except module.tk.TclError:
                continue
        if hasattr(self, "sync_workspace_nav"):
            self.sync_workspace_nav()
        if hasattr(self, "sync_workspace_sidebar"):
            self.sync_workspace_sidebar()

    module.App.apply_language = apply_language
    # Icons are the final presentation-only layer. Installing them here keeps
    # the established feature/i18n patch order unchanged and guarantees that
    # localized workspace labels already exist before sidebar decoration.
    apply_gui_icons(module)
