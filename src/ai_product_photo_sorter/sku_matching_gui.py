"""Desktop workspace for human-confirmed SKU/catalog candidate matching."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .sku_matching import (
    CONFIRMED_NAME,
    MANIFEST_NAME,
    clear_confirmation,
    confirm_candidate,
    generate_candidates,
    load_match_manifest,
)


_TEXT = {
    "en": {
        "tab": "SKU Match",
        "title": "SKU / Catalog Matching",
        "hint": (
            "Rank catalog candidates from approved product groups and local OCR/barcode evidence. "
            "Suggestions never become matches until you confirm them here."
        ),
        "approved": "Approved groups",
        "catalog": "Catalog",
        "evidence": "Local evidence",
        "browse": "Browse",
        "generate": "Generate candidates",
        "reload": "Reload",
        "confirm": "Confirm selected",
        "clear": "Clear confirmation",
        "open_confirmed": "Open confirmed CSV",
        "groups": "APPROVED PRODUCT GROUPS",
        "candidates": "RANKED CATALOG CANDIDATES",
        "idle": "Generate candidates from approved Review Center groups to start.",
        "pending": "Pending",
        "confirmed": "Confirmed",
        "working": "Ranking catalog candidates locally…",
    },
    "ar": {
        "tab": "مطابقة SKU",
        "title": "مطابقة SKU / الكتالوج",
        "hint": (
            "رتّب مرشحي الكتالوج اعتمادًا على المجموعات المعتمدة وأدلة OCR/Barcode المحلية. "
            "أي اقتراح يظل غير مثبت حتى تؤكده يدويًا من هنا."
        ),
        "approved": "المجموعات المعتمدة",
        "catalog": "ملف الكتالوج",
        "evidence": "أدلة OCR / Barcode",
        "browse": "اختيار",
        "generate": "ولّد المرشحين",
        "reload": "إعادة تحميل",
        "confirm": "أكد المرشح المحدد",
        "clear": "امسح التأكيد",
        "open_confirmed": "افتح CSV المؤكد",
        "groups": "مجموعات المنتجات المعتمدة",
        "candidates": "مرشحو الكتالوج المرتبون",
        "idle": "ولّد المرشحين من مجموعات Review Center المعتمدة للبدء.",
        "pending": "بانتظار التأكيد",
        "confirmed": "مؤكد",
        "working": "جاري ترتيب مرشحي الكتالوج محليًا…",
    },
    "zh": {
        "tab": "SKU 匹配",
        "title": "SKU / 目录匹配",
        "hint": "根据已批准产品组及本地 OCR/条码证据排序目录候选项。只有人工确认后才会成为匹配。",
        "approved": "已批准分组",
        "catalog": "目录文件",
        "evidence": "本地证据",
        "browse": "浏览",
        "generate": "生成候选项",
        "reload": "重新加载",
        "confirm": "确认所选项",
        "clear": "清除确认",
        "open_confirmed": "打开确认 CSV",
        "groups": "已批准产品组",
        "candidates": "排序后的目录候选项",
        "idle": "从 Review Center 已批准分组生成候选项以开始。",
        "pending": "待确认",
        "confirmed": "已确认",
        "working": "正在本地排序目录候选项…",
    },
}


def apply_sku_matching_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_set_running = module.App.set_running
    base_load_values = module.App.load_values

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self._sku_manifest = None
        self._sku_manifest_path = None
        self._sku_worker_running = False
        self.sku_status = module.tk.StringVar(value="")
        self.sku_approved_path = module.tk.StringVar(value="")
        self.sku_catalog_path = module.tk.StringVar(value="")
        self.sku_evidence_path = module.tk.StringVar(value="")
        self.sku_top_k = module.tk.StringVar(value="5")

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=18)
        self.main_tabs.add(page, text="SKU Match")
        self.sku_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        header.pack(fill="x")
        self.sku_title = module.ttk.Label(header, style="Metric.TLabel")
        self.sku_title.pack(anchor="w")
        self.sku_hint = module.ttk.Label(header, style="MetricName.TLabel", wraplength=1050)
        self.sku_hint.pack(anchor="w", pady=(5, 12))

        self.sku_path_labels = {}
        for key, variable, browse_command in (
            ("approved", self.sku_approved_path, self.browse_sku_approved),
            ("catalog", self.sku_catalog_path, self.browse_sku_catalog),
            ("evidence", self.sku_evidence_path, self.browse_sku_evidence),
        ):
            row = module.ttk.Frame(header, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            label = module.ttk.Label(row, style="MetricName.TLabel", width=18)
            label.pack(side="left", padx=(0, 8))
            self.sku_path_labels[key] = label
            module.ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))
            button = module.ttk.Button(row, style="Soft.TButton", command=browse_command)
            button.pack(side="left")
            setattr(self, f"sku_{key}_browse_button", button)

        actions = module.ttk.Frame(header, style="Card.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        module.ttk.Label(actions, text="Top K", style="MetricName.TLabel").pack(side="left", padx=(0, 6))
        module.ttk.Entry(actions, textvariable=self.sku_top_k, width=6).pack(side="left", padx=(0, 10))
        self.sku_generate_button = module.ttk.Button(
            actions, style="Accent.TButton", command=self.generate_sku_candidates
        )
        self.sku_generate_button.pack(side="left", padx=(0, 8))
        self.sku_reload_button = module.ttk.Button(
            actions, style="Soft.TButton", command=self.reload_sku_manifest
        )
        self.sku_reload_button.pack(side="left", padx=(0, 8))
        self.sku_open_confirmed_button = module.ttk.Button(
            actions, style="Soft.TButton", command=self.open_sku_confirmed
        )
        self.sku_open_confirmed_button.pack(side="left")
        module.ttk.Label(
            header,
            textvariable=self.sku_status,
            style="MetricName.TLabel",
            wraplength=1000,
        ).pack(anchor="w", pady=(10, 0))

        body = module.ttk.Frame(page, style="Panel.TFrame")
        body.pack(fill="both", expand=True, pady=(12, 0))
        left = module.ttk.Frame(body, style="Card.TFrame", padding=12)
        left.pack(side="left", fill="both", expand=False, padx=(0, 8))
        right = module.ttk.Frame(body, style="Card.TFrame", padding=12)
        right.pack(side="left", fill="both", expand=True)

        self.sku_groups_label = module.ttk.Label(left, style="MetricName.TLabel")
        self.sku_groups_label.pack(anchor="w", pady=(0, 8))
        self.sku_group_tree = module.ttk.Treeview(
            left,
            columns=("state", "model", "candidates"),
            show="tree headings",
            height=22,
            selectmode="browse",
        )
        self.sku_group_tree.heading("#0", text="Group")
        self.sku_group_tree.heading("state", text="State")
        self.sku_group_tree.heading("model", text="Model")
        self.sku_group_tree.heading("candidates", text="#")
        self.sku_group_tree.column("#0", width=225, stretch=True)
        self.sku_group_tree.column("state", width=95, anchor="center")
        self.sku_group_tree.column("model", width=100, anchor="w")
        self.sku_group_tree.column("candidates", width=45, anchor="center")
        self.sku_group_tree.pack(fill="both", expand=True)
        self.sku_group_tree.bind("<<TreeviewSelect>>", lambda _event: self.select_sku_group())

        self.sku_candidates_label = module.ttk.Label(right, style="MetricName.TLabel")
        self.sku_candidates_label.pack(anchor="w", pady=(0, 8))
        self.sku_candidate_tree = module.ttk.Treeview(
            right,
            columns=("score", "tier", "row", "reason"),
            show="headings",
            height=15,
            selectmode="browse",
        )
        self.sku_candidate_tree.heading("score", text="Score")
        self.sku_candidate_tree.heading("tier", text="Evidence")
        self.sku_candidate_tree.heading("row", text="Catalog row")
        self.sku_candidate_tree.heading("reason", text="Reason / product")
        self.sku_candidate_tree.column("score", width=70, anchor="center")
        self.sku_candidate_tree.column("tier", width=120, anchor="center")
        self.sku_candidate_tree.column("row", width=115, anchor="w")
        self.sku_candidate_tree.column("reason", width=520, stretch=True)
        self.sku_candidate_tree.pack(fill="both", expand=True)

        candidate_actions = module.ttk.Frame(right, style="Card.TFrame")
        candidate_actions.pack(fill="x", pady=(10, 0))
        self.sku_confirm_button = module.ttk.Button(
            candidate_actions, style="Accent.TButton", command=self.confirm_sku_selected
        )
        self.sku_confirm_button.pack(side="left", padx=(0, 8))
        self.sku_clear_button = module.ttk.Button(
            candidate_actions, style="Soft.TButton", command=self.clear_sku_confirmation
        )
        self.sku_clear_button.pack(side="left")

        self.sku_details = module.tk.Text(
            right,
            height=9,
            wrap="word",
            background=self.colors["panel2"],
            foreground=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            padx=10,
            pady=10,
        )
        self.sku_details.pack(fill="x", pady=(10, 0))
        self.sku_details.config(state="disabled")

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "sku_page"):
            return
        t = text(self)
        self.main_tabs.tab(self.sku_page, text=t["tab"])
        self.sku_title.config(text=t["title"])
        self.sku_hint.config(text=t["hint"])
        for key, label in self.sku_path_labels.items():
            label.config(text=t[key])
            getattr(self, f"sku_{key}_browse_button").config(text=t["browse"])
        self.sku_generate_button.config(text=t["generate"])
        self.sku_reload_button.config(text=t["reload"])
        self.sku_confirm_button.config(text=t["confirm"])
        self.sku_clear_button.config(text=t["clear"])
        self.sku_open_confirmed_button.config(text=t["open_confirmed"])
        self.sku_groups_label.config(text=t["groups"])
        self.sku_candidates_label.config(text=t["candidates"])
        if not self.sku_status.get():
            self.sku_status.set(t["idle"])

    def load_values(self):
        base_load_values(self)
        if not hasattr(self, "sku_approved_path"):
            return
        output_raw = self.vars["output"].get().strip() if self.vars.get("output") else ""
        if output_raw and not self.sku_approved_path.get().strip():
            approved = Path(output_raw).expanduser() / "approved_product_groups.csv"
            self.sku_approved_path.set(str(approved))
        prices = self.vars["prices"].get().strip() if self.vars.get("prices") else ""
        if prices and not self.sku_catalog_path.get().strip():
            self.sku_catalog_path.set(prices)
        if output_raw and not self.sku_evidence_path.get().strip():
            root = Path(output_raw).expanduser()
            candidates = [
                root / "local_catalog_evidence.json",
                root / "product_sorter_local_evidence" / "local_catalog_evidence.json",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    self.sku_evidence_path.set(str(candidate))
                    break

    def _browse_file(self, title, filetypes):
        raw = module.filedialog.askopenfilename(title=title, filetypes=filetypes)
        return raw or ""

    def browse_sku_approved(self):
        raw = _browse_file(self, "Select approved_product_groups.csv", [("CSV", "*.csv"), ("All files", "*.*")])
        if raw:
            self.sku_approved_path.set(raw)

    def browse_sku_catalog(self):
        raw = _browse_file(
            self,
            "Select product catalog",
            [("Catalog files", "*.xlsx *.xlsm *.csv"), ("Excel", "*.xlsx *.xlsm"), ("CSV", "*.csv"), ("All files", "*.*")],
        )
        if raw:
            self.sku_catalog_path.set(raw)

    def browse_sku_evidence(self):
        raw = _browse_file(self, "Select local_catalog_evidence.json", [("JSON", "*.json"), ("All files", "*.*")])
        if raw:
            self.sku_evidence_path.set(raw)

    def _selected_sku_group(self):
        selection = self.sku_group_tree.selection()
        return selection[0] if selection else ""

    def _selected_sku_candidate_row(self):
        selection = self.sku_candidate_tree.selection()
        return selection[0] if selection else ""

    def _sku_group(self, group_id):
        manifest = self._sku_manifest or {}
        for group in manifest.get("groups", []):
            if str(group.get("group_id")) == group_id:
                return group
        return None

    def _set_sku_details(self, value):
        self.sku_details.config(state="normal")
        self.sku_details.delete("1.0", "end")
        self.sku_details.insert("1.0", value)
        self.sku_details.config(state="disabled")

    def generate_sku_candidates(self):
        if self._sku_worker_running:
            return
        approved_raw = self.sku_approved_path.get().strip()
        catalog_raw = self.sku_catalog_path.get().strip()
        evidence_raw = self.sku_evidence_path.get().strip()
        if not approved_raw or not catalog_raw:
            module.messagebox.showerror("SKU Match", "Approved groups CSV and catalog file are required.")
            return
        try:
            top_k = int(self.sku_top_k.get().strip() or "5")
            if not 1 <= top_k <= 50:
                raise ValueError
        except ValueError:
            module.messagebox.showerror("SKU Match", "Top K must be an integer between 1 and 50.")
            return

        approved = Path(approved_raw)
        catalog = Path(catalog_raw)
        evidence = Path(evidence_raw) if evidence_raw else None
        output_raw = self.vars["output"].get().strip() if self.vars.get("output") else ""
        output_dir = Path(output_raw).expanduser() / "sku_matching" if output_raw else approved.expanduser().parent / "sku_matching"
        self._sku_worker_running = True
        self.sku_status.set(text(self)["working"])
        self.sku_generate_button.config(state="disabled")

        def worker():
            try:
                manifest, path = generate_candidates(
                    approved,
                    catalog,
                    evidence_json=evidence,
                    output_dir=output_dir,
                    top_k=top_k,
                )
                result = (manifest, path, None)
            except Exception as exc:
                result = (None, None, exc)
            self.root.after(0, lambda: self._finish_sku_generation(*result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_sku_generation(self, manifest, path, error):
        self._sku_worker_running = False
        self.sku_generate_button.config(state="normal")
        if error is not None:
            module.messagebox.showerror("SKU Match", str(error))
            self.sku_status.set(text(self)["idle"])
            return
        self._sku_manifest = manifest
        self._sku_manifest_path = path
        self.refresh_sku_matching()
        self.main_tabs.select(self.sku_page)

    def reload_sku_manifest(self):
        if self._sku_manifest_path is None:
            output_raw = self.vars["output"].get().strip() if self.vars.get("output") else ""
            candidate = Path(output_raw).expanduser() / "sku_matching" / MANIFEST_NAME if output_raw else None
            if candidate and candidate.is_file():
                self._sku_manifest_path = candidate
            else:
                raw = module.filedialog.askopenfilename(
                    title="Select sku_match_manifest.json",
                    filetypes=[("JSON", "*.json"), ("All files", "*.*")],
                )
                if not raw:
                    return
                self._sku_manifest_path = Path(raw)
        try:
            self._sku_manifest, self._sku_manifest_path = load_match_manifest(self._sku_manifest_path)
        except ValueError as exc:
            module.messagebox.showerror("SKU Match", str(exc))
            return
        self.refresh_sku_matching()

    def refresh_sku_matching(self):
        manifest = self._sku_manifest
        if not manifest:
            return
        selected = _selected_sku_group(self)
        self.sku_group_tree.delete(*self.sku_group_tree.get_children())
        t = text(self)
        for group in manifest.get("groups", []):
            group_id = str(group.get("group_id", ""))
            state = t["confirmed"] if group.get("decision", {}).get("status") == "confirmed" else t["pending"]
            self.sku_group_tree.insert(
                "",
                "end",
                iid=group_id,
                text=group_id,
                values=(state, group.get("model", ""), len(group.get("candidates", []))),
            )
        summary = manifest.get("summary", {})
        self.sku_status.set(
            f"SKU Match · {summary.get('confirmed_groups', 0)}/{summary.get('groups', 0)} confirmed · "
            f"{summary.get('groups_with_candidates', 0)} with candidates · "
            f"revision {manifest.get('revision', 0)} · auto-match OFF"
        )
        children = self.sku_group_tree.get_children()
        if selected and selected in children:
            self.sku_group_tree.selection_set(selected)
        elif children:
            self.sku_group_tree.selection_set(children[0])
        self.select_sku_group()

    def select_sku_group(self):
        group_id = _selected_sku_group(self)
        group = _sku_group(self, group_id)
        self.sku_candidate_tree.delete(*self.sku_candidate_tree.get_children())
        if group is None:
            _set_sku_details(self, "")
            return
        for candidate in group.get("candidates", []):
            row_id = str(candidate.get("row_id", ""))
            reason = " | ".join(candidate.get("reasons", []))
            display = str(candidate.get("display", ""))
            summary = f"{reason} — {display}" if reason else display
            self.sku_candidate_tree.insert(
                "",
                "end",
                iid=row_id,
                values=(
                    f"{float(candidate.get('ranking_score', 0.0)):.3f}",
                    candidate.get("tier", ""),
                    row_id,
                    summary,
                ),
            )
        decision = group.get("decision", {})
        confirmed_row = str(decision.get("row_id", ""))
        if confirmed_row and confirmed_row in self.sku_candidate_tree.get_children():
            self.sku_candidate_tree.selection_set(confirmed_row)
        elif self.sku_candidate_tree.get_children():
            self.sku_candidate_tree.selection_set(self.sku_candidate_tree.get_children()[0])
        evidence = group.get("evidence", {})
        _set_sku_details(
            self,
            "\n".join(
                [
                    f"Group: {group_id}",
                    f"Brand / model: {group.get('brand', '')} / {group.get('model', '')}",
                    f"Barcode evidence: {', '.join(evidence.get('barcodes', [])) or '—'}",
                    f"Labeled identifiers: {', '.join(evidence.get('labeled_identifiers', [])) or '—'}",
                    f"Decision: {decision.get('status', 'pending')} {confirmed_row}",
                    "Safety: suggestions only; automatic matching and publishing are disabled.",
                ]
            ),
        )

    def confirm_sku_selected(self):
        if self._sku_manifest_path is None:
            module.messagebox.showinfo("SKU Match", text(self)["idle"])
            return
        group_id = _selected_sku_group(self)
        row_id = _selected_sku_candidate_row(self)
        if not group_id or not row_id:
            module.messagebox.showinfo("SKU Match", "Select a product group and catalog candidate first.")
            return
        group = _sku_group(self, group_id)
        candidate = next((item for item in (group or {}).get("candidates", []) if item.get("row_id") == row_id), None)
        display = str((candidate or {}).get("display", row_id))
        if not module.messagebox.askyesno(
            "Confirm catalog match",
            f"Confirm this human-reviewed catalog match?\n\n{group_id}\n→ {row_id}\n{display}\n\nNo publish action will run.",
        ):
            return
        try:
            self._sku_manifest, self._sku_manifest_path = confirm_candidate(
                self._sku_manifest_path, group_id, row_id
            )
        except ValueError as exc:
            module.messagebox.showerror("SKU Match", str(exc))
            return
        self.refresh_sku_matching()

    def clear_sku_confirmation(self):
        if self._sku_manifest_path is None:
            return
        group_id = _selected_sku_group(self)
        if not group_id:
            return
        try:
            self._sku_manifest, self._sku_manifest_path = clear_confirmation(
                self._sku_manifest_path, group_id
            )
        except ValueError as exc:
            module.messagebox.showerror("SKU Match", str(exc))
            return
        self.refresh_sku_matching()

    def open_sku_confirmed(self):
        if self._sku_manifest_path is None:
            module.messagebox.showinfo("SKU Match", text(self)["idle"])
            return
        path = self._sku_manifest_path.parent / CONFIRMED_NAME
        if not path.is_file():
            module.messagebox.showinfo("SKU Match", "No confirmed CSV exists yet.")
            return
        try:
            if hasattr(module, "open_path"):
                module.open_path(path)
            else:
                import os
                import subprocess
                import sys
                if os.name == "nt":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(path)])
                else:
                    subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            module.messagebox.showerror("SKU Match", str(exc))

    def set_running(self, running):
        base_set_running(self, running)
        if not hasattr(self, "sku_generate_button"):
            return
        disabled = running or self._sku_worker_running
        self.sku_generate_button.config(state="disabled" if disabled else "normal")
        self.sku_confirm_button.config(state="disabled" if running else "normal")
        self.sku_clear_button.config(state="disabled" if running else "normal")

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.browse_sku_approved = browse_sku_approved
    module.App.browse_sku_catalog = browse_sku_catalog
    module.App.browse_sku_evidence = browse_sku_evidence
    module.App.generate_sku_candidates = generate_sku_candidates
    module.App._finish_sku_generation = _finish_sku_generation
    module.App.reload_sku_manifest = reload_sku_manifest
    module.App.refresh_sku_matching = refresh_sku_matching
    module.App.select_sku_group = select_sku_group
    module.App.confirm_sku_selected = confirm_sku_selected
    module.App.clear_sku_confirmation = clear_sku_confirmation
    module.App.open_sku_confirmed = open_sku_confirmed
    module.App.set_running = set_running
