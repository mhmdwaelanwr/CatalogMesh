"""Desktop GUI facade over the compatibility-preserved Tkinter implementation."""

from __future__ import annotations

import sys

from .paths import runtime_root
from . import setup_wizard as _setup_wizard  # ensure patched configuration paths
from . import _gui_impl as _impl
from . import environment_gui as _environment_gui
from .benchmark_gui import apply_benchmark_gui
from .provider_gui import apply_provider_gui
from .environment_gui import apply_environment_gui
from .ollama_gui import apply_ollama_gui, prepare_ollama_environment_fields
from .hybrid_gui import apply_hybrid_gui, prepare_hybrid_environment_fields
from .performance_gui import (
    apply_performance_gui,
    prepare_performance_environment_fields,
)
from .threshold_calibration_gui import apply_threshold_calibration_gui
from .hybrid_routing_gui import apply_hybrid_routing_gui
from .local_evidence_gui import apply_local_evidence_gui
from .review_center_gui import apply_review_center_gui
from .sku_matching_gui import apply_sku_matching_gui
from .catalog_exports_gui import apply_catalog_exports_gui
from .shopify_environment import prepare_shopify_environment_fields
from .shopify_publishing_gui import apply_shopify_publishing_gui
from .report_gui import apply_report_gui
from .report_autoload import apply_report_autoload

_impl.ROOT = runtime_root()
prepare_ollama_environment_fields(_environment_gui)
prepare_hybrid_environment_fields(_environment_gui)
prepare_performance_environment_fields(_environment_gui)
prepare_shopify_environment_fields(_environment_gui)

_REPORT_TEXT = {
    "en": (
        "Generate smart Markdown report",
        "One operation-wide SMART_REPORT.md: verified statistics plus one final text-only AI analysis call.",
    ),
    "ar": (
        "إنشاء تقرير Markdown ذكي شامل",
        "ملف SMART_REPORT.md واحد للعملية كلها: أرقام مؤكدة + تحليل AI نهائي بطلب نصي إضافي واحد.",
    ),
    "zh": (
        "生成智能 Markdown 报告",
        "每个任务生成一个 SMART_REPORT.md：可靠统计数据 + 最后一次纯文本 AI 分析调用。",
    ),
}

_base_configure_styles = _impl.App.configure_styles
_base_build = _impl.App.build
_base_apply_language = _impl.App.apply_language
_base_load_values = _impl.App.load_values
_base_collect = _impl.App.collect
_base_set_running = _impl.App.set_running


def _configure_styles(self):
    _base_configure_styles(self)
    style = _impl.ttk.Style(self.root)
    style.configure(
        "Card.TCheckbutton",
        background=self.colors["panel2"],
        foreground=self.colors["text"],
        font=("Sans", 10, "bold"),
    )
    style.map(
        "Card.TCheckbutton",
        background=[("active", self.colors["panel2"])],
        foreground=[("disabled", self.colors["muted"])],
    )


def _build(self):
    _base_build(self)
    setup_page = self.main_tabs.nametowidget(self.main_tabs.tabs()[0])
    children = setup_page.winfo_children()
    card = _impl.ttk.Frame(setup_page, style="Card.TFrame", padding=14)
    self.vars["md_report"] = _impl.tk.BooleanVar(value=False)
    self.report_checkbox = _impl.ttk.Checkbutton(
        card,
        variable=self.vars["md_report"],
        style="Card.TCheckbutton",
    )
    self.report_checkbox.pack(anchor="w")
    self.report_hint = _impl.ttk.Label(card, style="MetricName.TLabel", wraplength=900)
    self.report_hint.pack(anchor="w", pady=(4, 0))
    if len(children) >= 2:
        card.pack(fill="x", pady=(10, 8), before=children[1])
    else:
        card.pack(fill="x", pady=(10, 8))


def _apply_language(self):
    _base_apply_language(self)
    if hasattr(self, "report_checkbox"):
        title, hint = _REPORT_TEXT.get(self.lang, _REPORT_TEXT["en"])
        self.report_checkbox.config(text=title)
        self.report_hint.config(text=hint)


def _load_values(self):
    _base_load_values(self)
    if "md_report" in self.vars:
        enabled = str(self.values.get("PRODUCT_SORTER_MD_REPORT", "")).strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.vars["md_report"].set(enabled)


def _collect(self):
    values = _base_collect(self)
    if "md_report" in self.vars:
        values["PRODUCT_SORTER_MD_REPORT"] = (
            "true" if self.vars["md_report"].get() else "false"
        )
    return values


def _command(self):
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--cli-worker"]
    else:
        cmd = [sys.executable, str(_impl.ROOT / "product_sorter.py")]
    cmd += [
        "--non-interactive",
        "--source", self.vars["source"].get(),
        "--output", self.vars["output"].get(),
    ]
    if self.vars["prices"].get():
        cmd += ["--prices", self.vars["prices"].get()]
    if self.vars["sample"].get():
        cmd += ["--limit", self.vars["sample"].get()]
    if "md_report" in self.vars and self.vars["md_report"].get():
        cmd += ["--md-report"]
    return cmd


def _set_running(self, running):
    _base_set_running(self, running)
    if hasattr(self, "report_checkbox"):
        self.report_checkbox.config(state="disabled" if running else "normal")


_impl.App.configure_styles = _configure_styles
_impl.App.build = _build
_impl.App.apply_language = _apply_language
_impl.App.load_values = _load_values
_impl.App.collect = _collect
_impl.App.command = _command
_impl.App.set_running = _set_running
apply_benchmark_gui(_impl)
apply_provider_gui(_impl)
apply_environment_gui(_impl)
apply_ollama_gui(_impl)
apply_hybrid_gui(_impl)
apply_performance_gui(_impl)
apply_threshold_calibration_gui(_impl)
apply_hybrid_routing_gui(_impl)
apply_local_evidence_gui(_impl)
apply_review_center_gui(_impl)
apply_sku_matching_gui(_impl)
apply_catalog_exports_gui(_impl)
apply_shopify_publishing_gui(_impl)
apply_report_gui(_impl)
apply_report_autoload(_impl)

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
