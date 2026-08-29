"""Visual, non-destructive Review Center workspace."""

from __future__ import annotations

import json
from pathlib import Path
from tkinter import simpledialog
from typing import Any

from PIL import Image, ImageTk

from .review_center import (
    MANIFEST_NAME,
    REPORT_NAME,
    apply_review_plan,
    export_approved,
    initialize_review,
    load_manifest,
    review_summary,
)

_TEXT = {
    "en": {
        "tab": "Review",
        "title": "Review Center",
        "hint": "Visually verify product groups before catalog matching. Corrections update only the review manifest and audit log; photos are never moved by this workspace.",
        "open": "Open output",
        "reload": "Reload",
        "export": "Export approved",
        "approve": "Approve group",
        "unapprove": "Unapprove",
        "save_meta": "Save metadata",
        "set_view": "Set photo view",
        "move": "Move photo",
        "split": "Split photo",
        "merge": "Merge group",
        "groups": "PRODUCT GROUPS",
        "photos": "PHOTOS",
        "details": "GROUP DETAILS",
        "category": "Category",
        "brand": "Brand",
        "model": "Model",
        "notes": "Notes",
        "idle": "Open a Product Sorter output folder to start review.",
    },
    "ar": {
        "tab": "Review",
        "title": "مركز المراجعة",
        "hint": "راجع مجموعات المنتجات بصريًا قبل مطابقة الكتالوج. التصحيحات تعدّل Manifest وAudit Log فقط، ولا يتم نقل الصور من هذه الشاشة.",
        "open": "افتح مجلد النتائج",
        "reload": "إعادة تحميل",
        "export": "صدّر المعتمد",
        "approve": "اعتمد المجموعة",
        "unapprove": "إلغاء الاعتماد",
        "save_meta": "احفظ البيانات",
        "set_view": "عدّل زاوية الصورة",
        "move": "انقل الصورة",
        "split": "افصل الصورة",
        "merge": "ادمج المجموعة",
        "groups": "مجموعات المنتجات",
        "photos": "الصور",
        "details": "بيانات المجموعة",
        "category": "الفئة",
        "brand": "العلامة",
        "model": "الموديل",
        "notes": "ملاحظات",
        "idle": "افتح مجلد نتائج Product Sorter لبدء المراجعة.",
    },
    "zh": {
        "tab": "Review",
        "title": "审核中心",
        "hint": "在目录匹配前直观确认产品分组。修改仅写入审核清单和审计日志，本工作区不会移动照片。",
        "open": "打开输出目录",
        "reload": "重新加载",
        "export": "导出已批准组",
        "approve": "批准分组",
        "unapprove": "取消批准",
        "save_meta": "保存元数据",
        "set_view": "设置照片视角",
        "move": "移动照片",
        "split": "拆分照片",
        "merge": "合并分组",
        "groups": "产品分组",
        "photos": "照片",
        "details": "分组详情",
        "category": "类别",
        "brand": "品牌",
        "model": "型号",
        "notes": "备注",
        "idle": "打开 Product Sorter 输出目录开始审核。",
    },
}


def apply_review_center_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self._review_manifest = None
        self._review_manifest_path = None
        self._review_preview_image = None
        self.review_status = module.tk.StringVar(value="")
        self.review_category = module.tk.StringVar(value="")
        self.review_brand = module.tk.StringVar(value="")
        self.review_model = module.tk.StringVar(value="")
        self.review_notes = module.tk.StringVar(value="")

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=18)
        self.main_tabs.add(page, text="Review")
        self.review_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        header.pack(fill="x")
        self.review_title = module.ttk.Label(header, style="Metric.TLabel")
        self.review_title.pack(anchor="w")
        self.review_hint = module.ttk.Label(header, style="MetricName.TLabel", wraplength=1050)
        self.review_hint.pack(anchor="w", pady=(5, 12))
        actions = module.ttk.Frame(header, style="Card.TFrame")
        actions.pack(fill="x")
        self.review_open_button = module.ttk.Button(actions, style="Accent.TButton", command=self.open_review_output)
        self.review_open_button.pack(side="left", padx=(0, 8))
        self.review_reload_button = module.ttk.Button(actions, style="Soft.TButton", command=self.reload_review)
        self.review_reload_button.pack(side="left", padx=(0, 8))
        self.review_export_button = module.ttk.Button(actions, style="Soft.TButton", command=self.export_review_approved)
        self.review_export_button.pack(side="left")
        module.ttk.Label(header, textvariable=self.review_status, style="MetricName.TLabel", wraplength=1000).pack(anchor="w", pady=(10, 0))

        body = module.ttk.Frame(page, style="Panel.TFrame")
        body.pack(fill="both", expand=True, pady=(12, 0))
        left = module.ttk.Frame(body, style="Card.TFrame", padding=12)
        left.pack(side="left", fill="both", expand=False, padx=(0, 8))
        center = module.ttk.Frame(body, style="Card.TFrame", padding=12)
        center.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = module.ttk.Frame(body, style="Card.TFrame", padding=12)
        right.pack(side="left", fill="both", expand=True)

        self.review_groups_label = module.ttk.Label(left, style="MetricName.TLabel")
        self.review_groups_label.pack(anchor="w", pady=(0, 8))
        self.review_group_tree = module.ttk.Treeview(
            left,
            columns=("state", "category", "photos"),
            show="tree headings",
            height=20,
            selectmode="browse",
        )
        self.review_group_tree.heading("#0", text="Group")
        self.review_group_tree.heading("state", text="State")
        self.review_group_tree.heading("category", text="Category")
        self.review_group_tree.heading("photos", text="Photos")
        self.review_group_tree.column("#0", width=220, stretch=True)
        self.review_group_tree.column("state", width=82, anchor="center")
        self.review_group_tree.column("category", width=110, anchor="w")
        self.review_group_tree.column("photos", width=60, anchor="center")
        self.review_group_tree.pack(fill="both", expand=True)
        self.review_group_tree.bind("<<TreeviewSelect>>", lambda _event: self.select_review_group())

        self.review_photos_label = module.ttk.Label(center, style="MetricName.TLabel")
        self.review_photos_label.pack(anchor="w", pady=(0, 8))
        self.review_photo_tree = module.ttk.Treeview(
            center,
            columns=("view", "confidence", "status"),
            show="tree headings",
            height=12,
            selectmode="browse",
        )
        self.review_photo_tree.heading("#0", text="Filename")
        self.review_photo_tree.heading("view", text="View")
        self.review_photo_tree.heading("confidence", text="Confidence")
        self.review_photo_tree.heading("status", text="Original state")
        self.review_photo_tree.column("#0", width=250, stretch=True)
        self.review_photo_tree.column("view", width=90, anchor="center")
        self.review_photo_tree.column("confidence", width=90, anchor="center")
        self.review_photo_tree.column("status", width=110, anchor="center")
        self.review_photo_tree.pack(fill="x")
        self.review_photo_tree.bind("<<TreeviewSelect>>", lambda _event: self.select_review_photo())

        photo_actions = module.ttk.Frame(center, style="Card.TFrame")
        photo_actions.pack(fill="x", pady=(10, 8))
        self.review_view_button = module.ttk.Button(photo_actions, style="Soft.TButton", command=self.set_review_photo_view)
        self.review_view_button.pack(side="left", padx=(0, 6))
        self.review_move_button = module.ttk.Button(photo_actions, style="Soft.TButton", command=self.move_review_photo)
        self.review_move_button.pack(side="left", padx=(0, 6))
        self.review_split_button = module.ttk.Button(photo_actions, style="Soft.TButton", command=self.split_review_photo)
        self.review_split_button.pack(side="left")

        self.review_preview = module.ttk.Label(center, style="MetricName.TLabel", anchor="center", text="Select a photo")
        self.review_preview.pack(fill="both", expand=True, pady=(6, 0))

        self.review_details_label = module.ttk.Label(right, style="MetricName.TLabel")
        self.review_details_label.pack(anchor="w", pady=(0, 8))
        self.review_field_labels = {}
        for key, variable in (
            ("category", self.review_category),
            ("brand", self.review_brand),
            ("model", self.review_model),
            ("notes", self.review_notes),
        ):
            label = module.ttk.Label(right, style="MetricName.TLabel")
            label.pack(anchor="w", pady=(7, 2))
            self.review_field_labels[key] = label
            module.ttk.Entry(right, textvariable=variable, width=34).pack(fill="x")

        group_actions = module.ttk.Frame(right, style="Card.TFrame")
        group_actions.pack(fill="x", pady=(14, 0))
        self.review_save_meta_button = module.ttk.Button(group_actions, style="Soft.TButton", command=self.save_review_metadata)
        self.review_save_meta_button.pack(fill="x", pady=(0, 6))
        self.review_approve_button = module.ttk.Button(group_actions, style="Accent.TButton", command=lambda: self.set_review_approval(True))
        self.review_approve_button.pack(fill="x", pady=(0, 6))
        self.review_unapprove_button = module.ttk.Button(group_actions, style="Soft.TButton", command=lambda: self.set_review_approval(False))
        self.review_unapprove_button.pack(fill="x", pady=(0, 6))
        self.review_merge_button = module.ttk.Button(group_actions, style="Soft.TButton", command=self.merge_review_group)
        self.review_merge_button.pack(fill="x")

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "review_page"):
            return
        t = text(self)
        self.main_tabs.tab(self.review_page, text=t["tab"])
        self.review_title.config(text=t["title"])
        self.review_hint.config(text=t["hint"])
        self.review_open_button.config(text=t["open"])
        self.review_reload_button.config(text=t["reload"])
        self.review_export_button.config(text=t["export"])
        self.review_approve_button.config(text=t["approve"])
        self.review_unapprove_button.config(text=t["unapprove"])
        self.review_save_meta_button.config(text=t["save_meta"])
        self.review_view_button.config(text=t["set_view"])
        self.review_move_button.config(text=t["move"])
        self.review_split_button.config(text=t["split"])
        self.review_merge_button.config(text=t["merge"])
        self.review_groups_label.config(text=t["groups"])
        self.review_photos_label.config(text=t["photos"])
        self.review_details_label.config(text=t["details"])
        for key, label in self.review_field_labels.items():
            label.config(text=t[key])
        if not self.review_status.get():
            self.review_status.set(t["idle"])

    def _selected_group_id(self):
        selection = self.review_group_tree.selection()
        return selection[0] if selection else ""

    def _selected_photo_name(self):
        selection = self.review_photo_tree.selection()
        return selection[0] if selection else ""

    def _group_by_id(self, group_id):
        manifest = self._review_manifest or {}
        for group in manifest.get("groups", []):
            if str(group.get("group_id")) == group_id:
                return group
        return None

    def _review_plan(self, operations):
        path = self._review_manifest_path
        if path is None:
            raise ValueError("Open a review manifest first")
        plan_path = path.parent / ".product-sorter-review-gui-plan.json"
        try:
            plan_path.write_text(json.dumps({"operations": operations}, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest, resolved = apply_review_plan(path, plan_path)
        finally:
            try:
                plan_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._review_manifest = manifest
        self._review_manifest_path = resolved
        self.refresh_review()

    def open_review_output(self):
        current = Path(self.vars["output"].get()).expanduser() if self.vars.get("output") and self.vars["output"].get().strip() else None
        initial = str(current) if current and current.is_dir() else None
        raw = module.filedialog.askdirectory(title="Select Product Sorter output folder", initialdir=initial)
        if not raw:
            return
        root = Path(raw).expanduser().resolve()
        try:
            if (root / MANIFEST_NAME).is_file():
                manifest, path = load_manifest(root / MANIFEST_NAME)
            else:
                if not (root / REPORT_NAME).is_file():
                    raise ValueError(f"{REPORT_NAME} was not found in {root}")
                manifest, path = initialize_review(root)
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))
            return
        self._review_manifest = manifest
        self._review_manifest_path = path
        self.refresh_review()
        self.main_tabs.select(self.review_page)

    def reload_review(self):
        if self._review_manifest_path is None:
            self.open_review_output()
            return
        try:
            self._review_manifest, self._review_manifest_path = load_manifest(self._review_manifest_path)
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))
            return
        self.refresh_review()

    def refresh_review(self):
        manifest = self._review_manifest
        if not manifest:
            return
        selected = _selected_group_id(self)
        self.review_group_tree.delete(*self.review_group_tree.get_children())
        for group in manifest.get("groups", []):
            group_id = str(group.get("group_id", ""))
            state = "approved" if group.get("approved") else "pending"
            self.review_group_tree.insert(
                "",
                "end",
                iid=group_id,
                text=group_id,
                values=(state, group.get("category", ""), len(group.get("photos", []))),
            )
        summary = review_summary(manifest)
        self.review_status.set(
            f"Review · {summary['approved_groups']}/{summary['groups']} approved · "
            f"{summary['photos']} photos · revision {summary['revision']} · "
            f"catalog_ready={summary['catalog_ready']}"
        )
        children = self.review_group_tree.get_children()
        target = selected if selected in children else (children[0] if children else "")
        if target:
            self.review_group_tree.selection_set(target)
            self.review_group_tree.focus(target)
            self.select_review_group()
        else:
            self.review_photo_tree.delete(*self.review_photo_tree.get_children())

    def select_review_group(self):
        group = _group_by_id(self, _selected_group_id(self))
        if group is None:
            return
        self.review_category.set(str(group.get("category", "")))
        self.review_brand.set(str(group.get("brand", "")))
        self.review_model.set(str(group.get("model", "")))
        self.review_notes.set(str(group.get("notes", "")))
        self.review_photo_tree.delete(*self.review_photo_tree.get_children())
        for photo in group.get("photos", []):
            filename = str(photo.get("filename", ""))
            self.review_photo_tree.insert(
                "",
                "end",
                iid=filename,
                text=filename,
                values=(
                    photo.get("view", "unknown"),
                    f"{float(photo.get('confidence', 0.0)):.2f}",
                    photo.get("original_status", ""),
                ),
            )
        children = self.review_photo_tree.get_children()
        if children:
            self.review_photo_tree.selection_set(children[0])
            self.review_photo_tree.focus(children[0])
            self.select_review_photo()

    def select_review_photo(self):
        filename = _selected_photo_name(self)
        group = _group_by_id(self, _selected_group_id(self))
        if not filename or group is None:
            return
        photo = next((item for item in group.get("photos", []) if item.get("filename") == filename), None)
        if photo is None:
            return
        root = Path(str((self._review_manifest or {}).get("output_root", "")))
        path = root / str(photo.get("relative_path", ""))
        if not path.is_file():
            self._review_preview_image = None
            self.review_preview.config(image="", text=f"Preview unavailable\n{path}")
            return
        try:
            with Image.open(path) as original:
                image = original.convert("RGB")
                image.thumbnail((430, 300), Image.Resampling.LANCZOS)
                preview = ImageTk.PhotoImage(image)
        except OSError as exc:
            self._review_preview_image = None
            self.review_preview.config(image="", text=f"Preview error: {exc}")
            return
        self._review_preview_image = preview
        self.review_preview.config(image=preview, text="")

    def save_review_metadata(self):
        group_id = _selected_group_id(self)
        if not group_id:
            return
        try:
            _review_plan(
                self,
                [
                    {
                        "action": "set_group",
                        "group": group_id,
                        "category": self.review_category.get(),
                        "brand": self.review_brand.get(),
                        "model": self.review_model.get(),
                        "notes": self.review_notes.get(),
                    }
                ],
            )
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))

    def set_review_approval(self, approved):
        group_id = _selected_group_id(self)
        if not group_id:
            return
        try:
            _review_plan(self, [{"action": "approve" if approved else "unapprove", "group": group_id}])
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))

    def set_review_photo_view(self):
        filename = _selected_photo_name(self)
        if not filename:
            return
        group = _group_by_id(self, _selected_group_id(self))
        photo = next((item for item in (group or {}).get("photos", []) if item.get("filename") == filename), None)
        value = simpledialog.askstring("Review Center", "Photo view", initialvalue=str((photo or {}).get("view", "unknown")), parent=self.root)
        if value is None:
            return
        try:
            _review_plan(self, [{"action": "set_view", "filename": filename, "view": value}])
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))

    def move_review_photo(self):
        filename = _selected_photo_name(self)
        current = _selected_group_id(self)
        if not filename or not current:
            return
        destination = simpledialog.askstring("Review Center", "Move photo to group id", parent=self.root)
        if not destination:
            return
        try:
            _review_plan(self, [{"action": "move_photo", "filename": filename, "to_group": destination.strip()}])
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))

    def split_review_photo(self):
        filename = _selected_photo_name(self)
        group_id = _selected_group_id(self)
        group = _group_by_id(self, group_id)
        if not filename or group is None:
            return
        if len(group.get("photos", [])) <= 1:
            module.messagebox.showinfo("Review Center", "This group contains only one photo.")
            return
        new_group = simpledialog.askstring("Review Center", "New group id", initialvalue=f"{group_id}_split", parent=self.root)
        if not new_group:
            return
        try:
            _review_plan(self, [{"action": "split", "group": group_id, "filenames": [filename], "new_group": new_group.strip()}])
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))

    def merge_review_group(self):
        group_id = _selected_group_id(self)
        if not group_id:
            return
        other = simpledialog.askstring("Review Center", "Merge another group into this group", parent=self.root)
        if not other:
            return
        try:
            _review_plan(self, [{"action": "merge", "groups": [group_id, other.strip()], "target": group_id}])
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))

    def export_review_approved(self):
        if self._review_manifest_path is None:
            module.messagebox.showinfo("Review Center", text(self)["idle"])
            return
        try:
            summary, path = export_approved(self._review_manifest_path)
        except ValueError as exc:
            module.messagebox.showerror("Review Center", str(exc))
            return
        module.messagebox.showinfo(
            "Review Center",
            f"Approved groups: {summary['approved_groups']}\nPending: {summary['pending_groups']}\n\n{path}",
        )

    def set_running(self, running):
        base_set_running(self, running)
        state = "disabled" if running else "normal"
        for name in (
            "review_open_button",
            "review_reload_button",
            "review_export_button",
            "review_approve_button",
            "review_unapprove_button",
            "review_save_meta_button",
            "review_view_button",
            "review_move_button",
            "review_split_button",
            "review_merge_button",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.open_review_output = open_review_output
    module.App.reload_review = reload_review
    module.App.refresh_review = refresh_review
    module.App.select_review_group = select_review_group
    module.App.select_review_photo = select_review_photo
    module.App.save_review_metadata = save_review_metadata
    module.App.set_review_approval = set_review_approval
    module.App.set_review_photo_view = set_review_photo_view
    module.App.move_review_photo = move_review_photo
    module.App.split_review_photo = split_review_photo
    module.App.merge_review_group = merge_review_group
    module.App.export_review_approved = export_review_approved
    module.App.set_running = set_running
