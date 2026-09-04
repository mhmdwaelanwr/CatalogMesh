"""Desktop workspace for safe offline catalog export profiles."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .catalog_exports import EXPORT_MANIFEST, generate_exports


_TEXT = {
    "en": {
        "tab": "Exports",
        "title": "Catalog Export Profiles",
        "hint": "Generate offline files only from human-confirmed SKU matches. Shopify output is always draft and unpublished; local photos remain an upload manifest until public URLs exist.",
        "manifest": "SKU match manifest",
        "output": "Export folder",
        "profile": "Profile",
        "browse": "Browse",
        "generate": "Generate exports",
        "open": "Open export folder",
        "idle": "No export generated yet.",
        "working": "Validating confirmed products and generating safe export files…",
    },
    "ar": {
        "tab": "التصدير",
        "title": "ملفات تصدير الكتالوج",
        "hint": "أنشئ ملفات Offline فقط من مطابقات SKU المؤكدة بشريًا. ملف Shopify يظل Draft وغير منشور، والصور المحلية تخرج في Manifest منفصل حتى تتوفر روابط عامة.",
        "manifest": "ملف SKU Match",
        "output": "مجلد التصدير",
        "profile": "نوع التصدير",
        "browse": "اختيار",
        "generate": "إنشاء ملفات التصدير",
        "open": "افتح مجلد التصدير",
        "idle": "لا يوجد تصدير حتى الآن.",
        "working": "جاري التحقق من المنتجات المؤكدة وإنشاء ملفات التصدير الآمنة…",
    },
    "zh": {
        "tab": "导出",
        "title": "目录导出配置",
        "hint": "仅从人工确认的 SKU 匹配生成离线文件。Shopify 始终为草稿且不发布；本地图片仅进入上传清单。",
        "manifest": "SKU 匹配清单",
        "output": "导出目录",
        "profile": "配置",
        "browse": "浏览",
        "generate": "生成导出文件",
        "open": "打开导出目录",
        "idle": "尚未生成导出。",
        "working": "正在验证已确认产品并生成安全导出文件…",
    },
}

_PROFILE_VALUES = {
    "All safe profiles": "all",
    "Shopify draft CSV": "shopify",
    "Neutral PIM CSV": "pim",
}


def apply_catalog_exports_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self._export_worker_running = False
        self._latest_export_manifest = None
        self.export_manifest_path = module.tk.StringVar(value="")
        self.export_output_path = module.tk.StringVar(value="")
        self.export_profile = module.tk.StringVar(value="All safe profiles")
        self.export_status = module.tk.StringVar(value="")

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=22)
        self.main_tabs.add(page, text="Exports")
        self.export_page = page

        card = module.ttk.Frame(page, style="Card.TFrame", padding=20)
        card.pack(fill="x", anchor="n")
        self.export_title = module.ttk.Label(card, style="Metric.TLabel")
        self.export_title.pack(anchor="w")
        self.export_hint = module.ttk.Label(card, style="MetricName.TLabel", wraplength=1050)
        self.export_hint.pack(anchor="w", pady=(5, 16))

        self.export_path_labels = {}
        for key, variable, command in (
            ("manifest", self.export_manifest_path, self.browse_export_manifest),
            ("output", self.export_output_path, self.browse_export_output),
        ):
            row = module.ttk.Frame(card, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            label = module.ttk.Label(row, style="MetricName.TLabel", width=20)
            label.pack(side="left", padx=(0, 8))
            self.export_path_labels[key] = label
            module.ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))
            button = module.ttk.Button(row, style="Soft.TButton", command=command)
            button.pack(side="left")
            setattr(self, f"export_{key}_browse_button", button)

        actions = module.ttk.Frame(card, style="Card.TFrame")
        actions.pack(fill="x", pady=(12, 0))
        self.export_profile_label = module.ttk.Label(actions, style="MetricName.TLabel")
        self.export_profile_label.pack(side="left", padx=(0, 8))
        self.export_profile_box = module.ttk.Combobox(
            actions,
            textvariable=self.export_profile,
            values=list(_PROFILE_VALUES),
            state="readonly",
            width=22,
        )
        self.export_profile_box.pack(side="left", padx=(0, 12))
        self.export_generate_button = module.ttk.Button(
            actions, style="Accent.TButton", command=self.generate_catalog_exports
        )
        self.export_generate_button.pack(side="left", padx=(0, 8))
        self.export_open_button = module.ttk.Button(
            actions, style="Soft.TButton", command=self.open_export_folder
        )
        self.export_open_button.pack(side="left")

        warning = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        warning.pack(fill="x", pady=(12, 0))
        self.export_safety_label = module.ttk.Label(
            warning,
            style="MetricName.TLabel",
            wraplength=1050,
            text=(
                "Safety: no network publishing. Shopify rows are Status=draft and Published on online store=false. "
                "Inventory, shipping/tax promises, and public image URLs are never invented."
            ),
        )
        self.export_safety_label.pack(anchor="w")
        module.ttk.Label(
            warning,
            textvariable=self.export_status,
            style="Metric.TLabel",
            wraplength=1050,
        ).pack(anchor="w", pady=(10, 0))

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "export_page"):
            return
        t = text(self)
        self.main_tabs.tab(self.export_page, text=t["tab"])
        self.export_title.config(text=t["title"])
        self.export_hint.config(text=t["hint"])
        for key, label in self.export_path_labels.items():
            label.config(text=t[key])
            getattr(self, f"export_{key}_browse_button").config(text=t["browse"])
        self.export_profile_label.config(text=t["profile"])
        self.export_generate_button.config(text=t["generate"])
        self.export_open_button.config(text=t["open"])
        if not self.export_status.get():
            self.export_status.set(t["idle"])

    def load_values(self):
        base_load_values(self)
        if not hasattr(self, "export_manifest_path"):
            return
        output_raw = self.vars["output"].get().strip() if self.vars.get("output") else ""
        if output_raw:
            root = Path(output_raw).expanduser()
            if not self.export_manifest_path.get().strip():
                self.export_manifest_path.set(str(root / "sku_matching" / "sku_match_manifest.json"))
            if not self.export_output_path.get().strip():
                self.export_output_path.set(str(root / "exports"))

    def browse_export_manifest(self):
        raw = module.filedialog.askopenfilename(
            title="Select sku_match_manifest.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if raw:
            self.export_manifest_path.set(raw)

    def browse_export_output(self):
        raw = module.filedialog.askdirectory(title="Select export folder")
        if raw:
            self.export_output_path.set(raw)

    def generate_catalog_exports(self):
        if self._export_worker_running:
            return
        manifest_raw = self.export_manifest_path.get().strip()
        output_raw = self.export_output_path.get().strip()
        if not manifest_raw:
            module.messagebox.showerror("Exports", "SKU match manifest is required.")
            return
        profile = _PROFILE_VALUES.get(self.export_profile.get(), "all")
        self._export_worker_running = True
        self.export_generate_button.config(state="disabled")
        self.export_status.set(text(self)["working"])

        def worker():
            try:
                summary, path = generate_exports(
                    Path(manifest_raw),
                    output_dir=Path(output_raw) if output_raw else None,
                    profile=profile,
                )
                result = (summary, path, None)
            except Exception as exc:
                result = (None, None, exc)
            self.root.after(0, lambda: self._finish_catalog_exports(*result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_catalog_exports(self, summary, path, error):
        self._export_worker_running = False
        self.export_generate_button.config(state="normal")
        if error is not None:
            self.export_status.set(text(self)["idle"])
            module.messagebox.showerror("Exports", str(error))
            return
        self._latest_export_manifest = path
        self.export_output_path.set(str(path.parent))
        self.export_status.set(
            f"Generated {summary['products']} confirmed products · Shopify=draft/unpublished · "
            f"{summary['local_images_requiring_upload']} local images require upload · publish OFF"
        )
        self.main_tabs.select(self.export_page)

    def open_export_folder(self):
        raw = self.export_output_path.get().strip()
        if not raw and self._latest_export_manifest is not None:
            raw = str(self._latest_export_manifest.parent)
        if not raw:
            module.messagebox.showinfo("Exports", text(self)["idle"])
            return
        path = Path(raw).expanduser()
        if not path.exists():
            module.messagebox.showinfo("Exports", text(self)["idle"])
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            module.messagebox.showerror("Exports", str(exc))

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "export_generate_button"):
            self.export_generate_button.config(
                state="disabled" if running or self._export_worker_running else "normal"
            )

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.browse_export_manifest = browse_export_manifest
    module.App.browse_export_output = browse_export_output
    module.App.generate_catalog_exports = generate_catalog_exports
    module.App._finish_catalog_exports = _finish_catalog_exports
    module.App.open_export_folder = open_export_folder
    module.App.set_running = set_running
