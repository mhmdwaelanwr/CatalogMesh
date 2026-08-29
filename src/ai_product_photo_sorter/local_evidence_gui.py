"""Benchmark Center UI for local OCR + barcode evidence."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .local_evidence import backend_status, install_hint, scan_source

_TEXT = {
    "en": {
        "title": "Local OCR + Barcode Evidence",
        "hint": "Extract text, SKU/model-like tokens and EAN/UPC/Code128/QR/DataMatrix values locally. Evidence only: no catalog match or grouping change.",
        "run": "Scan local evidence",
        "idle": "No local evidence scan has been run yet.",
        "running": "Scanning locally…",
    },
    "ar": {
        "title": "أدلة OCR + Barcode محلية",
        "hint": "استخرج النصوص ورموز SKU/Model وEAN/UPC/Code128/QR/DataMatrix محليًا. Evidence فقط: لا يتم مطابقة كتالوج أو تغيير التجميع.",
        "run": "افحص الأدلة محليًا",
        "idle": "لم يتم تشغيل فحص الأدلة المحلية بعد.",
        "running": "جاري الفحص محليًا…",
    },
    "zh": {
        "title": "本地 OCR + 条码证据",
        "hint": "在本机提取文本、SKU/型号候选项以及 EAN/UPC/Code128/QR/DataMatrix。仅生成证据，不自动匹配目录或修改分组。",
        "run": "扫描本地证据",
        "idle": "尚未运行本地证据扫描。",
        "running": "正在本地扫描…",
    },
}


def apply_local_evidence_gui(module: Any) -> None:
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
        card = module.ttk.Frame(page, style="Card.TFrame", padding=20)
        card.pack(fill="x", anchor="n", pady=(14, 0))
        self.local_evidence_card = card
        self.local_evidence_status = module.tk.StringVar(value="")
        self.local_evidence_ocr = module.tk.BooleanVar(value=True)
        self.local_evidence_barcode = module.tk.BooleanVar(value=True)

        self.local_evidence_title = module.ttk.Label(card, style="Metric.TLabel")
        self.local_evidence_title.pack(anchor="w")
        self.local_evidence_hint = module.ttk.Label(
            card, style="MetricName.TLabel", wraplength=900
        )
        self.local_evidence_hint.pack(anchor="w", pady=(5, 12))

        toggles = module.ttk.Frame(card, style="Card.TFrame")
        toggles.pack(fill="x", pady=(0, 10))
        self.local_evidence_ocr_check = module.ttk.Checkbutton(
            toggles, text="OCR", variable=self.local_evidence_ocr
        )
        self.local_evidence_ocr_check.pack(side="left")
        self.local_evidence_barcode_check = module.ttk.Checkbutton(
            toggles, text="Barcode / QR", variable=self.local_evidence_barcode
        )
        self.local_evidence_barcode_check.pack(side="left", padx=(14, 0))

        self.local_evidence_button = module.ttk.Button(
            card, style="Accent.TButton", command=self.run_local_evidence
        )
        self.local_evidence_button.pack(anchor="w")
        module.ttk.Label(
            card,
            textvariable=self.local_evidence_status,
            style="MetricName.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(12, 0))

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "local_evidence_card"):
            return
        t = text(self)
        self.local_evidence_title.config(text=t["title"])
        self.local_evidence_hint.config(text=t["hint"])
        self.local_evidence_button.config(text=t["run"])
        if not self.local_evidence_status.get():
            self.local_evidence_status.set(t["idle"])

    def finish(self, *, summary=None, json_path=None, csv_path=None, error=None):
        self._local_evidence_busy = False
        self.set_running(False)
        if error is not None:
            self.local_evidence_status.set(str(error))
            module.messagebox.showerror("Local Evidence", str(error))
            return
        status = (
            f"Local evidence · photos {summary['photos']} · OCR hits {summary['ocr_photo_hits']} · "
            f"barcode hits {summary['barcode_photo_hits']} · candidates {summary['candidate_photo_hits']}"
        )
        self.local_evidence_status.set(status)
        module.messagebox.showinfo(
            "Local Evidence",
            status
            + "\n\nEvidence only: production catalog matching remains disabled."
            + f"\n\nJSON: {json_path}\nCSV: {csv_path}",
        )

    def run_local_evidence(self):
        if getattr(self, "_local_evidence_busy", False):
            return
        use_ocr = bool(self.local_evidence_ocr.get())
        use_barcode = bool(self.local_evidence_barcode.get())
        if not use_ocr and not use_barcode:
            module.messagebox.showerror("Local Evidence", "Enable OCR and/or Barcode.")
            return
        status = backend_status()
        missing = []
        if use_ocr and not (status["rapidocr"] and status["onnxruntime"]):
            missing.append("RapidOCR + ONNX Runtime")
        if use_barcode and not status["zxingcpp"]:
            missing.append("ZXing-C++")
        if missing:
            module.messagebox.showerror(
                "Local Evidence",
                "Missing optional local runtime: " + ", ".join(missing)
                + "\n\nInstall with:\n" + install_hint(),
            )
            return

        source_raw = module.filedialog.askdirectory(title="Select product photo folder")
        if not source_raw:
            return
        output_raw = module.filedialog.askdirectory(title="Select local evidence output folder")
        if not output_raw:
            return
        source = Path(source_raw).expanduser().resolve()
        output = Path(output_raw).expanduser().resolve()
        self._local_evidence_busy = True
        self.local_evidence_status.set(text(self)["running"])
        self.set_running(True)

        def worker():
            try:
                summary, json_path, csv_path = scan_source(
                    source,
                    output_dir=output,
                    use_ocr=use_ocr,
                    use_barcode=use_barcode,
                )
            except Exception as exc:
                self.root.after(0, lambda: finish(self, error=exc))
                return
            self.root.after(
                0,
                lambda: finish(
                    self,
                    summary=summary,
                    json_path=json_path,
                    csv_path=csv_path,
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "local_evidence_button"):
            self.local_evidence_button.config(state="disabled" if running else "normal")
        if hasattr(self, "local_evidence_ocr_check"):
            state = "disabled" if running else "normal"
            self.local_evidence_ocr_check.config(state=state)
            self.local_evidence_barcode_check.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.run_local_evidence = run_local_evidence
    module.App.set_running = set_running
