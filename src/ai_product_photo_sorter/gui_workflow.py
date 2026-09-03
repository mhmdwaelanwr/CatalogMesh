"""Final GUI workflow ordering and Arabic RTL display adaptation."""
from __future__ import annotations

from typing import Any, Iterable

from .arabic_ui import (
    arabic_visual_fix_enabled,
    prepare_loaded_gui_catalogs,
    shape_arabic_for_tk,
)


WORKSPACE_USAGE_ORDER = (
    "Operation setup",
    "Models & API keys",
    "Results & activity",
    "Review",
    "SKU Match",
    "Exports",
    "Automation",
    "Reports",
    "Benchmark",
    "Environment",
    "About",
)

WORKSPACE_LABEL_ALIASES = {
    "Operation setup": ("Operation setup", "Setup"),
    "Models & API keys": ("Models & API keys", "API"),
    "Results & activity": ("Results & activity", "Results"),
}


def workspace_usage_order(records: Iterable[tuple[str, str]]) -> tuple[str, ...]:
    """Return tab IDs ordered by the common product-catalog workflow.

    The first three legacy notebook pages are created as ``Setup``, ``API``,
    and ``Results`` and receive their full labels only during the language
    pass. Resolve both names here so ordering is correct before localization.
    Unknown future tabs remain available and are appended in existing order.
    """
    items = [(str(tab_id), str(label).strip()) for tab_id, label in records]
    by_label = {label.casefold(): tab_id for tab_id, label in items}
    ordered: list[str] = []
    for label in WORKSPACE_USAGE_ORDER:
        aliases = WORKSPACE_LABEL_ALIASES.get(label, (label,))
        tab_id = next(
            (by_label.get(alias.casefold()) for alias in aliases if by_label.get(alias.casefold()) is not None),
            None,
        )
        if tab_id is not None and tab_id not in ordered:
            ordered.append(tab_id)
    ordered.extend(tab_id for tab_id, _label in items if tab_id not in ordered)
    return tuple(ordered)


def apply_gui_workflow(module: Any) -> None:
    """Install usage-first tab order and Linux Arabic shaping without drift."""
    prepare_loaded_gui_catalogs("ai_product_photo_sorter")

    base_t = module.App.t
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_change_lang = module.App.change_lang

    def t(self, key):
        logical = base_t(self, key)
        if self.lang == "ar":
            return shape_arabic_for_tk(logical)
        return logical

    def _move_tabs(self, order):
        """Move existing notebook tabs into an exact deterministic order."""
        selected = self.main_tabs.select()
        # Repeatedly inserting the desired tab at the current position works
        # when the requested list already contains every notebook child. The
        # usage resolver guarantees that invariant, including unknown tabs.
        for index, tab_id in enumerate(order):
            try:
                current = self.main_tabs.index(tab_id)
                if current != index:
                    self.main_tabs.insert(index, tab_id)
            except module.tk.TclError:
                continue
        if selected:
            try:
                self.main_tabs.select(selected)
            except module.tk.TclError:
                pass

    def _set_language_selector_display(self):
        arabic_label = shape_arabic_for_tk("العربية")
        values = (arabic_label, "English", "中文")
        self.langbox.configure(values=values)
        selected = {"ar": arabic_label, "en": "English", "zh": "中文"}.get(
            self.lang,
            "English",
        )
        self.langbox.set(selected)
        try:
            self.langbox.configure(justify="right" if self.lang == "ar" else "left")
        except module.tk.TclError:
            pass

    def build(self):
        base_build(self)
        records = [
            (tab_id, self.main_tabs.tab(tab_id, "text"))
            for tab_id in self.main_tabs.tabs()
        ]
        # Several legacy language hooks still use numeric tab indexes. Keep the
        # original build order so it can be restored briefly before each
        # translation pass, then apply the usage-first order afterward.
        self._legacy_workspace_order = tuple(tab_id for tab_id, _label in records)
        self._usage_workspace_order = workspace_usage_order(records)
        _set_language_selector_display(self)

    def apply_language(self):
        if hasattr(self, "_legacy_workspace_order"):
            _move_tabs(self, self._legacy_workspace_order)

        base_apply_language(self)

        if hasattr(self, "_usage_workspace_order"):
            _move_tabs(self, self._usage_workspace_order)

        # The desktop/window manager on Linux already handles BiDi for the
        # native title bar. Keep that one logical while Tk labels/tabs receive
        # shaped visual-order Arabic.
        try:
            logical_title = module.L.get(self.lang, module.L["en"])["title"]
            self.root.title(logical_title)
        except Exception:
            pass

        _set_language_selector_display(self)

        if hasattr(self, "workspace_nav_label"):
            label = {"ar": "مساحة العمل", "en": "Workspace", "zh": "工作区"}.get(
                self.lang,
                "Workspace",
            )
            if self.lang == "ar":
                label = shape_arabic_for_tk(label)
            self.workspace_nav_label.configure(text=label)
            try:
                self.workspace_nav.configure(
                    justify="right" if self.lang == "ar" else "left"
                )
            except module.tk.TclError:
                pass
            self.sync_workspace_nav()

    def change_lang(self, event=None):
        selected = self.langbox.get()
        arabic_label = shape_arabic_for_tk("العربية")
        mapping = {
            "العربية": "ar",
            arabic_label: "ar",
            "English": "en",
            "中文": "zh",
        }
        language = mapping.get(selected)
        if language is None:
            return base_change_lang(self, event)
        self.lang = language
        self.apply_language()

    module.App.t = t
    module.App.build = build
    module.App.apply_language = apply_language
    module.App.change_lang = change_lang
    module.App._move_tabs = _move_tabs
    module.App._set_language_selector_display = _set_language_selector_display

    # Expose the effective mode for diagnostics/tests without changing any
    # sorter behavior or external connector boundaries.
    module.ARABIC_VISUAL_FIX_ENABLED = arabic_visual_fix_enabled()
