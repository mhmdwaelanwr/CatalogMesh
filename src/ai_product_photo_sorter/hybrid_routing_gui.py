"""Benchmark Center UI for Hybrid Routing Lab simulation evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .hybrid_routing_lab import simulate_from_files

_TEXT = {
    "en": {
        "title": "Hybrid Routing Lab",
        "hint": "Simulate calibrated local same/different decisions and measure how much boundary work could stay local. Ambiguous boundaries remain on Vision. Production routing is never enabled here.",
        "run": "Simulate routing",
        "idle": "No routing simulation has been run yet.",
    },
    "ar": {
        "title": "معمل Hybrid Routing",
        "hint": "حاكي قرارات same/different المحلية بالـthresholds المعايرة وقِس قد إيه من شغل الحدود ممكن يفضل Local. الحالات الغامضة تفضل للـVision، والـProduction Routing لا يتم تفعيله من هنا.",
        "run": "شغّل محاكاة الـRouting",
        "idle": "لم يتم تشغيل محاكاة Routing بعد.",
    },
    "zh": {
        "title": "Hybrid Routing 实验室",
        "hint": "使用校准阈值模拟本地 same/different 决策，测量可本地处理的边界工作量。模糊边界仍交给 Vision，本工具不会启用生产路由。",
        "run": "运行路由模拟",
        "idle": "尚未运行路由模拟。",
    },
}


def apply_hybrid_routing_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        page = getattr(self, "benchmark_page", None)
        if page is None:
            return
        self.routing_lab_status = module.tk.StringVar(value="")
        card = module.ttk.Frame(page, style="Card.TFrame", padding=20)
        card.pack(fill="x", anchor="n", pady=(14, 0))
        self.routing_lab_card = card
        self.routing_lab_title = module.ttk.Label(card, style="Metric.TLabel")
        self.routing_lab_title.pack(anchor="w")
        self.routing_lab_hint = module.ttk.Label(
            card, style="MetricName.TLabel", wraplength=900
        )
        self.routing_lab_hint.pack(anchor="w", pady=(5, 14))
        self.routing_lab_button = module.ttk.Button(
            card,
            style="Accent.TButton",
            command=self.simulate_hybrid_routing,
        )
        self.routing_lab_button.pack(anchor="w")
        module.ttk.Label(
            card,
            textvariable=self.routing_lab_status,
            style="MetricName.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(12, 0))

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "routing_lab_card"):
            return
        t = text(self)
        self.routing_lab_title.config(text=t["title"])
        self.routing_lab_hint.config(text=t["hint"])
        self.routing_lab_button.config(text=t["run"])
        if not self.routing_lab_status.get():
            self.routing_lab_status.set(t["idle"])

    def simulate_hybrid_routing(self):
        shadow_raw = module.filedialog.askopenfilename(
            title="Select hybrid_embedding_shadow.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not shadow_raw:
            return
        shadow = Path(shadow_raw).expanduser().resolve()

        calibration_raw = module.filedialog.askopenfilename(
            title="Select hybrid_threshold_calibration.json",
            initialdir=str(shadow.parent),
            filetypes=[("JSON files", "*.json")],
        )
        if not calibration_raw:
            return
        calibration = Path(calibration_raw).expanduser().resolve()

        truth = getattr(self, "_calibration_ground_truth", None)
        if truth is not None and not truth.is_file():
            truth = None
        try:
            summary, json_path, md_path, csv_path = simulate_from_files(
                shadow,
                calibration,
                ground_truth=truth,
                output_dir=shadow.parent,
            )
        except (ValueError, OSError) as exc:
            module.messagebox.showerror("Hybrid Routing Lab", str(exc))
            return

        coverage = float(summary["local_routing_coverage"])
        accuracy = summary.get("local_routing_accuracy")
        accuracy_text = "n/a" if accuracy is None else f"{float(accuracy):.1%}"
        status = (
            f"Simulation · local {summary['local_routed_boundaries']}/{summary['adjacent_boundaries']} "
            f"({coverage:.1%}) · Vision {summary['vision_boundaries_remaining']} · "
            f"local accuracy {accuracy_text} · misroutes {summary['unsafe_local_misroutes']}"
        )
        self.routing_lab_status.set(status)
        module.messagebox.showinfo(
            "Hybrid Routing Lab",
            status
            + "\n\nSimulation only: no provider calls were skipped and production routing remains disabled."
            + f"\n\nReport: {md_path}\nJSON: {json_path}\nCSV: {csv_path}",
        )

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "routing_lab_button"):
            self.routing_lab_button.config(state="disabled" if running else "normal")

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.simulate_hybrid_routing = simulate_hybrid_routing
    module.App.set_running = set_running
