"""Tkinter-safe visual refinement inspired by the CatalogMesh Figma spec.

This module only restyles/reorders widgets already owned by their original
parents.  It intentionally avoids Canvas-based re-parenting and custom drawing
so the desktop stays stable across Windows, Linux and macOS Tk builds.
"""
from __future__ import annotations

from typing import Any

_TEXT = {
    "en": ("Operation setup", "Choose the workspace, routing strategy and run options. Advanced controls remain available below."),
    "ar": ("إعداد العملية", "اختر مساحة العمل واستراتيجية التوجيه وخيارات التشغيل. تظل الإعدادات المتقدمة متاحة بالأسفل."),
    "zh": ("任务设置", "选择工作区、路由策略和运行选项。高级控制仍可在下方使用。"),
}


def apply_design_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_configure_styles = module.App.configure_styles

    def configure_styles(self):
        base_configure_styles(self)
        style = module.ttk.Style(self.root)
        style.configure("PageTitle.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=("Sans", 18, "bold"))
        style.configure("PageSubtitle.TLabel", background=self.colors["panel"], foreground=self.colors["muted"], font=("Sans", 9))
        style.configure("WorkflowCard.TFrame", background=self.colors["panel2"], relief="flat")

    def build(self):
        base_build(self)
        tabs = self.main_tabs.tabs()
        if not tabs:
            return
        setup = self.main_tabs.nametowidget(tabs[0])
        existing = list(setup.pack_slaves())
        self.operation_heading = module.ttk.Frame(setup, style="Panel.TFrame")
        self.operation_title = module.ttk.Label(self.operation_heading, style="PageTitle.TLabel")
        self.operation_title.pack(anchor="w")
        self.operation_subtitle = module.ttk.Label(self.operation_heading, style="PageSubtitle.TLabel", wraplength=900)
        self.operation_subtitle.pack(anchor="w", pady=(2, 0))
        if existing:
            self.operation_heading.pack(fill="x", pady=(0, 12), before=existing[0])
        else:
            self.operation_heading.pack(fill="x", pady=(0, 12))
        # Reuse the existing base form/action/progress containers as cards.
        for child in existing[:3]:
            try:
                child.configure(style="Card.TFrame", padding=14)
            except module.tk.TclError:
                try:
                    child.configure(style="Card.TFrame")
                except module.tk.TclError:
                    pass

    def apply_language(self):
        base_apply_language(self)
        if hasattr(self, "operation_title"):
            title, subtitle = _TEXT.get(self.lang, _TEXT["en"])
            self.operation_title.configure(text=title)
            self.operation_subtitle.configure(text=subtitle)

    module.App.configure_styles = configure_styles
    module.App.build = build
    module.App.apply_language = apply_language
