"""Desktop workspace for guarded Shopify remote preview, draft staging and publish."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .shopify_publishing import (
    API_VERSION,
    ShopifyClient,
    _credentials,
    publish_staged,
    remote_preview,
    rollback_publication,
    stage_drafts,
)

_TEXT = {
    "en": {
        "tab": "Shopify",
        "title": "Shopify Publishing · Guarded Remote Stage",
        "hint": "Preview first. Remote staging writes DRAFT products only. Publishing is a separate explicit action and inventory is never changed by this workspace.",
        "export": "Export manifest",
        "output": "Remote state folder",
        "store": "Store domain",
        "publication": "Publication ID",
        "browse": "Browse",
        "preview": "Remote preview",
        "stage": "Stage drafts",
        "publish": "Publish staged",
        "rollback": "Rollback publish",
        "open": "Open state folder",
        "idle": "No Shopify remote action has run yet.",
        "working": "Running guarded Shopify operation…",
        "missing": "Configure SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_ACCESS_TOKEN in Environment Center first.",
    },
    "ar": {
        "tab": "Shopify",
        "title": "نشر Shopify · مرحلة Remote محمية",
        "hint": "ابدأ بالمعاينة. مرحلة Remote تنشئ أو تحدّث المنتجات كـ Draft فقط. النشر خطوة منفصلة بتأكيد صريح ولا يتم تعديل المخزون من هنا.",
        "export": "ملف Export Manifest",
        "output": "مجلد حالة Shopify",
        "store": "دومين المتجر",
        "publication": "Publication ID",
        "browse": "اختيار",
        "preview": "معاينة Remote",
        "stage": "تجهيز Drafts",
        "publish": "نشر المنتجات المجهزة",
        "rollback": "إلغاء النشر",
        "open": "فتح مجلد الحالة",
        "idle": "لم يتم تنفيذ عملية Shopify Remote بعد.",
        "working": "جاري تنفيذ عملية Shopify المحمية…",
        "missing": "اضبط SHOPIFY_STORE_DOMAIN و SHOPIFY_ADMIN_ACCESS_TOKEN من Environment Center أولًا.",
    },
    "zh": {
        "tab": "Shopify",
        "title": "Shopify 发布 · 受保护远程阶段",
        "hint": "先预览。远程阶段只写入 DRAFT 产品；发布必须单独明确确认，本工作区不会修改库存。",
        "export": "导出清单",
        "output": "远程状态目录",
        "store": "商店域名",
        "publication": "Publication ID",
        "browse": "浏览",
        "preview": "远程预览",
        "stage": "暂存草稿",
        "publish": "发布已暂存产品",
        "rollback": "回滚发布",
        "open": "打开状态目录",
        "idle": "尚未执行 Shopify 远程操作。",
        "working": "正在执行受保护的 Shopify 操作…",
        "missing": "请先在 Environment Center 配置 SHOPIFY_STORE_DOMAIN 和 SHOPIFY_ADMIN_ACCESS_TOKEN。",
    },
}


def apply_shopify_publishing_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self._shopify_worker_running = False
        self.shopify_export_path = module.tk.StringVar(value="")
        self.shopify_output_path = module.tk.StringVar(value="")
        self.shopify_store = module.tk.StringVar(value="")
        self.shopify_publication = module.tk.StringVar(value="")
        self.shopify_status = module.tk.StringVar(value="")

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=22)
        self.main_tabs.add(page, text="Shopify")
        self.shopify_page = page

        card = module.ttk.Frame(page, style="Card.TFrame", padding=20)
        card.pack(fill="x", anchor="n")
        self.shopify_title = module.ttk.Label(card, style="Metric.TLabel")
        self.shopify_title.pack(anchor="w")
        self.shopify_hint = module.ttk.Label(card, style="MetricName.TLabel", wraplength=1050)
        self.shopify_hint.pack(anchor="w", pady=(5, 16))

        self.shopify_labels = {}
        rows = (
            ("export", self.shopify_export_path, True, self.browse_shopify_export),
            ("output", self.shopify_output_path, True, self.browse_shopify_output),
            ("store", self.shopify_store, False, None),
            ("publication", self.shopify_publication, False, None),
        )
        for key, variable, has_browse, command in rows:
            row = module.ttk.Frame(card, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            label = module.ttk.Label(row, style="MetricName.TLabel", width=20)
            label.pack(side="left", padx=(0, 8))
            self.shopify_labels[key] = label
            module.ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))
            if has_browse:
                button = module.ttk.Button(row, style="Soft.TButton", command=command)
                button.pack(side="left")
                setattr(self, f"shopify_{key}_browse_button", button)

        actions = module.ttk.Frame(card, style="Card.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        self.shopify_preview_button = module.ttk.Button(actions, style="Soft.TButton", command=self.preview_shopify_remote)
        self.shopify_preview_button.pack(side="left", padx=(0, 7))
        self.shopify_stage_button = module.ttk.Button(actions, style="Accent.TButton", command=self.stage_shopify_drafts)
        self.shopify_stage_button.pack(side="left", padx=(0, 7))
        self.shopify_publish_button = module.ttk.Button(actions, style="Danger.TButton", command=self.publish_shopify_staged)
        self.shopify_publish_button.pack(side="left", padx=(0, 7))
        self.shopify_rollback_button = module.ttk.Button(actions, style="Soft.TButton", command=self.rollback_shopify_publish)
        self.shopify_rollback_button.pack(side="left", padx=(0, 7))
        self.shopify_open_button = module.ttk.Button(actions, style="Soft.TButton", command=self.open_shopify_folder)
        self.shopify_open_button.pack(side="left")

        warning = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        warning.pack(fill="x", pady=(12, 0))
        module.ttk.Label(
            warning,
            style="MetricName.TLabel",
            wraplength=1050,
            text=(
                "Safety: preview performs queries only. Stage requires explicit confirmation and keeps products DRAFT. "
                "Publish requires typing PUBLISH. Rollback requires typing UNPUBLISH. Inventory writes are disabled."
            ),
        ).pack(anchor="w")
        module.ttk.Label(warning, textvariable=self.shopify_status, style="Metric.TLabel", wraplength=1050).pack(anchor="w", pady=(10, 0))

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "shopify_page"):
            return
        t = text(self)
        self.main_tabs.tab(self.shopify_page, text=t["tab"])
        self.shopify_title.config(text=t["title"])
        self.shopify_hint.config(text=t["hint"])
        for key, label in self.shopify_labels.items():
            label.config(text=t[key])
        for key in ("export", "output"):
            getattr(self, f"shopify_{key}_browse_button").config(text=t["browse"])
        self.shopify_preview_button.config(text=t["preview"])
        self.shopify_stage_button.config(text=t["stage"])
        self.shopify_publish_button.config(text=t["publish"])
        self.shopify_rollback_button.config(text=t["rollback"])
        self.shopify_open_button.config(text=t["open"])
        if not self.shopify_status.get():
            self.shopify_status.set(t["idle"])

    def load_values(self):
        base_load_values(self)
        if not hasattr(self, "shopify_export_path"):
            return
        self.shopify_store.set(str(self.values.get("SHOPIFY_STORE_DOMAIN", "")))
        self.shopify_publication.set(str(self.values.get("SHOPIFY_PUBLICATION_ID", "")))
        output_raw = self.vars["output"].get().strip() if self.vars.get("output") else ""
        if output_raw:
            root = Path(output_raw).expanduser()
            if not self.shopify_export_path.get().strip():
                self.shopify_export_path.set(str(root / "exports" / "catalog_export_manifest.json"))
            if not self.shopify_output_path.get().strip():
                self.shopify_output_path.set(str(root / "exports" / "shopify_remote"))

    def browse_shopify_export(self):
        raw = module.filedialog.askopenfilename(title="Select catalog_export_manifest.json", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if raw:
            self.shopify_export_path.set(raw)

    def browse_shopify_output(self):
        raw = module.filedialog.askdirectory(title="Select Shopify remote state folder")
        if raw:
            self.shopify_output_path.set(raw)

    def _shopify_client(self):
        domain = self.shopify_store.get().strip() or str(self.values.get("SHOPIFY_STORE_DOMAIN", ""))
        token = str(self.values.get("SHOPIFY_ADMIN_ACCESS_TOKEN", "")) or os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")
        try:
            domain, token = _credentials(domain, token)
        except ValueError as exc:
            raise ValueError(text(self)["missing"]) from exc
        api_version = str(self.values.get("SHOPIFY_API_VERSION", "")).strip() or API_VERSION
        return ShopifyClient(domain, token, api_version=api_version)

    def _run_shopify(self, action, worker):
        if self._shopify_worker_running:
            return
        self._shopify_worker_running = True
        self._set_shopify_buttons("disabled")
        self.shopify_status.set(text(self)["working"])

        def target():
            try:
                result = worker()
                payload = (action, result, None)
            except Exception as exc:
                payload = (action, None, exc)
            self.root.after(0, lambda: self._finish_shopify(*payload))

        threading.Thread(target=target, daemon=True).start()

    def _finish_shopify(self, action, result, error):
        self._shopify_worker_running = False
        self._set_shopify_buttons("normal")
        if error is not None:
            self.shopify_status.set(text(self)["idle"])
            module.messagebox.showerror("Shopify", str(error))
            return
        payload, path = result
        self.shopify_output_path.set(str(path.parent))
        if action == "preview":
            blocked = sum(item.get("action") == "blocked_duplicate_sku" for item in payload.get("products", []))
            self.shopify_status.set(f"Preview complete · {len(payload.get('products', []))} products · writes 0 · blocked duplicates {blocked}")
        else:
            products = payload.get("products", {})
            published = sum(bool(item.get("published")) for item in products.values())
            self.shopify_status.set(f"{action} complete · managed {len(products)} · published {published} · inventory writes 0")
        self.main_tabs.select(self.shopify_page)

    def _set_shopify_buttons(self, state):
        for name in ("preview", "stage", "publish", "rollback"):
            button = getattr(self, f"shopify_{name}_button", None)
            if button is not None:
                button.config(state=state)

    def preview_shopify_remote(self):
        export = self.shopify_export_path.get().strip()
        if not export:
            module.messagebox.showerror("Shopify", "Catalog export manifest is required.")
            return
        def worker():
            return remote_preview(Path(export), self._shopify_client(), output_dir=Path(self.shopify_output_path.get()) if self.shopify_output_path.get().strip() else None)
        self._run_shopify("preview", worker)

    def stage_shopify_drafts(self):
        export = self.shopify_export_path.get().strip()
        if not export:
            module.messagebox.showerror("Shopify", "Catalog export manifest is required.")
            return
        approved = module.messagebox.askyesno(
            "Shopify · Stage drafts",
            "This will perform remote writes to Shopify, but products will remain DRAFT and unpublished. Continue?",
        )
        if not approved:
            return
        def worker():
            return stage_drafts(Path(export), self._shopify_client(), output_dir=Path(self.shopify_output_path.get()) if self.shopify_output_path.get().strip() else None)
        self._run_shopify("stage", worker)

    def publish_shopify_staged(self):
        output = self.shopify_output_path.get().strip()
        publication = self.shopify_publication.get().strip()
        if not output or not publication:
            module.messagebox.showerror("Shopify", "Remote state folder and Publication ID are required.")
            return
        typed = module.simpledialog.askstring("Shopify · Publish", "Type PUBLISH exactly to activate and publish all staged products:")
        if typed != "PUBLISH":
            return
        state = Path(output) / "shopify_publish_manifest.json"
        def worker():
            return publish_staged(state, self._shopify_client(), publication_id=publication, confirmation="PUBLISH")
        self._run_shopify("publish", worker)

    def rollback_shopify_publish(self):
        output = self.shopify_output_path.get().strip()
        if not output:
            module.messagebox.showerror("Shopify", "Remote state folder is required.")
            return
        typed = module.simpledialog.askstring("Shopify · Rollback", "Type UNPUBLISH exactly to unpublish managed products and return them to DRAFT:")
        if typed != "UNPUBLISH":
            return
        state = Path(output) / "shopify_publish_manifest.json"
        def worker():
            return rollback_publication(state, self._shopify_client(), confirmation="UNPUBLISH")
        self._run_shopify("rollback", worker)

    def open_shopify_folder(self):
        raw = self.shopify_output_path.get().strip()
        if not raw:
            module.messagebox.showinfo("Shopify", text(self)["idle"])
            return
        path = Path(raw).expanduser()
        if not path.exists():
            module.messagebox.showinfo("Shopify", text(self)["idle"])
            return
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            module.messagebox.showerror("Shopify", str(exc))

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "shopify_preview_button"):
            self._set_shopify_buttons("disabled" if running or self._shopify_worker_running else "normal")

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.browse_shopify_export = browse_shopify_export
    module.App.browse_shopify_output = browse_shopify_output
    module.App._shopify_client = _shopify_client
    module.App._run_shopify = _run_shopify
    module.App._finish_shopify = _finish_shopify
    module.App._set_shopify_buttons = _set_shopify_buttons
    module.App.preview_shopify_remote = preview_shopify_remote
    module.App.stage_shopify_drafts = stage_shopify_drafts
    module.App.publish_shopify_staged = publish_shopify_staged
    module.App.rollback_shopify_publish = rollback_shopify_publish
    module.App.open_shopify_folder = open_shopify_folder
    module.App.set_running = set_running
