"""Benchmark Center controls for labeled datasets and hybrid threshold calibration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .threshold_calibration import (
    DEFAULT_MIN_BOUNDARIES,
    DEFAULT_MIN_DECISIONS,
    DEFAULT_MIN_PRECISION,
    calibrate_from_files,
    validate_ground_truth,
    write_ground_truth_template,
)

_TEXT = {
    "en": {
        "title": "Dataset & threshold calibration",
        "hint": "Create product-group labels from a real shoot, validate coverage, then calibrate conservative Hybrid Shadow thresholds from measured similarities.",
        "precision": "Minimum precision",
        "prepare": "Prepare label CSV",
        "validate": "Validate labels",
        "calibrate": "Calibrate thresholds",
        "idle": "No labeled dataset selected yet.",
    },
    "ar": {
        "title": "الداتا ومعايرة الـthresholds",
        "hint": "أنشئ ملف labels من تصوير منتجات حقيقي، راجع اكتمال product_group، ثم استخرج thresholds محافظة من نتائج Hybrid Shadow المقاسة.",
        "precision": "أقل Precision مطلوبة",
        "prepare": "جهّز ملف Labels",
        "validate": "راجع الـLabels",
        "calibrate": "عاير الـThresholds",
        "idle": "لم يتم اختيار dataset معلّمة بعد.",
    },
    "zh": {
        "title": "数据集与阈值校准",
        "hint": "从真实商品拍摄创建产品组标签，验证覆盖率，再根据 Hybrid Shadow 相似度校准保守阈值。",
        "precision": "最低精确率",
        "prepare": "生成标签 CSV",
        "validate": "验证标签",
        "calibrate": "校准阈值",
        "idle": "尚未选择已标注数据集。",
    },
}


def apply_threshold_calibration_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self._calibration_ground_truth: Path | None = None
        self.vars["calibration_min_precision"] = module.tk.StringVar(
            value=str(DEFAULT_MIN_PRECISION)
        )
        self.calibration_status = module.tk.StringVar(value="")

        page = getattr(self, "benchmark_page", None)
        if page is None:
            return
        card = module.ttk.Frame(page, style="Card.TFrame", padding=20)
        card.pack(fill="x", anchor="n", pady=(14, 0))
        self.calibration_card = card
        self.calibration_title = module.ttk.Label(card, style="Metric.TLabel")
        self.calibration_title.pack(anchor="w")
        self.calibration_hint = module.ttk.Label(
            card, style="MetricName.TLabel", wraplength=900
        )
        self.calibration_hint.pack(anchor="w", pady=(5, 14))

        row = module.ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        self.calibration_precision_label = module.ttk.Label(
            row, style="MetricName.TLabel"
        )
        self.calibration_precision_label.pack(side="left", padx=(0, 8))
        self.calibration_precision_entry = module.ttk.Entry(
            row, textvariable=self.vars["calibration_min_precision"], width=8
        )
        self.calibration_precision_entry.pack(side="left", padx=(0, 14))
        self.calibration_prepare_button = module.ttk.Button(
            row, style="Soft.TButton", command=self.prepare_ground_truth_labels
        )
        self.calibration_prepare_button.pack(side="left", padx=(0, 8))
        self.calibration_validate_button = module.ttk.Button(
            row, style="Soft.TButton", command=self.validate_ground_truth_labels
        )
        self.calibration_validate_button.pack(side="left", padx=(0, 8))
        self.calibration_run_button = module.ttk.Button(
            row, style="Accent.TButton", command=self.calibrate_hybrid_thresholds
        )
        self.calibration_run_button.pack(side="left")
        module.ttk.Label(
            card,
            textvariable=self.calibration_status,
            style="MetricName.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(12, 0))

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "calibration_card"):
            return
        t = text(self)
        self.calibration_title.config(text=t["title"])
        self.calibration_hint.config(text=t["hint"])
        self.calibration_precision_label.config(text=t["precision"])
        self.calibration_prepare_button.config(text=t["prepare"])
        self.calibration_validate_button.config(text=t["validate"])
        self.calibration_run_button.config(text=t["calibrate"])
        if not self.calibration_status.get():
            self.calibration_status.set(t["idle"])

    def source_path(self) -> Path | None:
        raw = self.vars.get("source")
        text_value = raw.get().strip() if raw is not None else ""
        if not text_value:
            module.messagebox.showerror("Calibration", "Choose the product photo source folder first.")
            return None
        source = Path(text_value).expanduser().resolve()
        if not source.is_dir():
            module.messagebox.showerror("Calibration", f"Source folder does not exist:\n{source}")
            return None
        return source

    def minimum_precision(self) -> float | None:
        try:
            value = float(self.vars["calibration_min_precision"].get().strip())
        except (ValueError, KeyError):
            value = -1.0
        if not 0.5 <= value <= 1.0:
            module.messagebox.showerror(
                "Calibration", "Minimum precision must be between 0.5 and 1.0."
            )
            return None
        return value

    def prepare_ground_truth_labels(self):
        source = source_path(self)
        if source is None:
            return
        target_raw = module.filedialog.asksaveasfilename(
            title="Save Product Sorter ground truth",
            initialdir=str(source.parent),
            initialfile="product_sorter_ground_truth.csv",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not target_raw:
            return
        target = Path(target_raw)
        try:
            summary = write_ground_truth_template(source, target)
        except (ValueError, OSError) as exc:
            module.messagebox.showerror("Calibration", str(exc))
            return
        self._calibration_ground_truth = target.resolve()
        self.calibration_status.set(
            f"Label template created · {summary['photos']} photos · fill product_group for every row"
        )
        module.messagebox.showinfo(
            "Calibration",
            "Ground-truth CSV created. Fill product_group for every photo before calibration.\n\n"
            f"{target}",
        )

    def choose_ground_truth(self) -> Path | None:
        current = getattr(self, "_calibration_ground_truth", None)
        initialdir = str(current.parent) if current else (
            self.vars.get("source").get().strip() if self.vars.get("source") is not None else ""
        )
        selected = module.filedialog.askopenfilename(
            title="Select labeled ground truth CSV",
            initialdir=initialdir or None,
            filetypes=[("CSV files", "*.csv")],
        )
        if not selected:
            return None
        path = Path(selected).expanduser().resolve()
        self._calibration_ground_truth = path
        return path

    def validate_ground_truth_labels(self):
        source = source_path(self)
        if source is None:
            return
        truth = choose_ground_truth(self)
        if truth is None:
            return
        try:
            summary = validate_ground_truth(source, truth)
        except (ValueError, OSError) as exc:
            module.messagebox.showerror("Calibration", str(exc))
            return
        coverage = float(summary["product_group_coverage"])
        message = (
            f"Labels · {summary['product_group_labeled']}/{summary['source_photos']} photos · "
            f"{summary['unique_product_groups']} groups · coverage {coverage:.1%}"
        )
        self.calibration_status.set(message)
        if summary["valid_for_calibration"]:
            module.messagebox.showinfo("Calibration", message + "\n\nDataset is structurally ready for calibration.")
        else:
            details = []
            if summary["missing_filenames"]:
                details.append(f"missing rows: {len(summary['missing_filenames'])}")
            if summary["unknown_filenames"]:
                details.append(f"unknown files: {len(summary['unknown_filenames'])}")
            if summary["duplicate_filenames"]:
                details.append(f"duplicates: {len(summary['duplicate_filenames'])}")
            if coverage < 1.0:
                details.append("product_group labels are incomplete")
            module.messagebox.showwarning(
                "Calibration", message + "\n\n" + ", ".join(details)
            )

    def calibrate_hybrid_thresholds(self):
        precision = minimum_precision(self)
        if precision is None:
            return
        shadow_raw = module.filedialog.askopenfilename(
            title="Select hybrid_embedding_shadow.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not shadow_raw:
            return
        shadow = Path(shadow_raw).expanduser().resolve()
        truth = getattr(self, "_calibration_ground_truth", None)
        if truth is None or not truth.is_file():
            selected = module.filedialog.askopenfilename(
                title="Optional ground truth CSV (Cancel if truth is embedded in shadow evidence)",
                filetypes=[("CSV files", "*.csv")],
            )
            truth = Path(selected).expanduser().resolve() if selected else None
            self._calibration_ground_truth = truth
        try:
            result, json_path, md_path = calibrate_from_files(
                shadow,
                ground_truth=truth,
                output_dir=shadow.parent,
                minimum_precision=precision,
                minimum_boundaries=DEFAULT_MIN_BOUNDARIES,
                minimum_decisions=DEFAULT_MIN_DECISIONS,
            )
        except (ValueError, OSError) as exc:
            module.messagebox.showerror("Calibration", str(exc))
            return

        if result.get("recommendation_available"):
            same = float(result["same_threshold"])
            different = float(result["different_threshold"])
            if "HYBRID_SIMILARITY_SAME" in self.vars:
                self.vars["HYBRID_SIMILARITY_SAME"].set(f"{same:.6f}")
            if "HYBRID_SIMILARITY_DIFFERENT" in self.vars:
                self.vars["HYBRID_SIMILARITY_DIFFERENT"].set(f"{different:.6f}")
            status = (
                f"Recommendation · same >= {same:.4f} · different <= {different:.4f} · "
                f"coverage {float(result['confident_coverage']):.1%} · "
                f"confident accuracy {float(result['confident_accuracy']):.1%}"
            )
            self.calibration_status.set(status)
            module.messagebox.showinfo(
                "Calibration",
                status
                + "\n\nValues were copied into the Hybrid Shadow fields only. Production routing remains disabled."
                + f"\n\nReport: {md_path}\nJSON: {json_path}",
            )
        else:
            self.calibration_status.set("No safe threshold pair met the requested precision gate.")
            module.messagebox.showwarning(
                "Calibration",
                "No safe threshold pair met the requested precision gate. Keep Hybrid Shadow Mode enabled and collect more labeled data."
                + f"\n\nReport: {md_path}",
            )

    def set_running(self, running):
        base_set_running(self, running)
        if not hasattr(self, "calibration_prepare_button"):
            return
        state = "disabled" if running else "normal"
        self.calibration_prepare_button.config(state=state)
        self.calibration_validate_button.config(state=state)
        self.calibration_run_button.config(state=state)
        self.calibration_precision_entry.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.prepare_ground_truth_labels = prepare_ground_truth_labels
    module.App.validate_ground_truth_labels = validate_ground_truth_labels
    module.App.calibrate_hybrid_thresholds = calibrate_hybrid_thresholds
    module.App.set_running = set_running
