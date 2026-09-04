"""CatalogMesh Storage Center backed by the local rclone CLI."""
from __future__ import annotations

from pathlib import Path
import subprocess
import threading
from typing import Any

from .rclone_storage import (
    RcloneError,
    TransferOptions,
    append_sync_audit,
    list_remotes,
    remote_target,
    rclone_version,
    stream_transfer,
    test_remote,
)


_TEXT = {
    "en": {
        "tab": "Storage",
        "title": "Cloud Storage · rclone",
        "hint": "Keep processing and resume data local, then copy completed output to any configured rclone remote. Automatic upload is copy-only and never deletes remote files.",
        "binary": "rclone status",
        "not_checked": "Not checked yet",
        "not_found": "rclone is not available",
        "remote": "Configured remote",
        "remote_path": "Remote base folder",
        "local_output": "Local output",
        "mode": "Manual transfer mode",
        "copy": "Copy · safe, no remote deletions",
        "sync": "Sync mirror · may delete remote extras",
        "auto": "Copy output automatically after a successful sorting run",
        "auto_hint": "Automatic mode always uses rclone copy, even when manual mode is set to Sync.",
        "bandwidth": "Bandwidth limit (optional, e.g. 10M)",
        "transfers": "Parallel transfers",
        "checkers": "Parallel checkers",
        "refresh": "Refresh remotes",
        "test": "Test remote",
        "preview": "Dry-run preview",
        "upload": "Upload now",
        "cancel": "Cancel transfer",
        "idle": "Storage is idle",
        "checking": "Checking rclone…",
        "testing": "Testing remote…",
        "running_copy": "Copying output to cloud…",
        "running_sync": "Synchronizing mirror…",
        "running_preview": "Previewing transfer…",
        "success": "Storage transfer completed",
        "preview_done": "Dry-run preview completed",
        "failed": "Storage transfer failed",
        "cancelled": "Storage transfer cancelled",
        "choose_remote": "Choose a configured rclone remote first.",
        "choose_output": "Choose a valid local output folder first.",
        "sync_title": "Confirm destructive mirror",
        "sync_prompt": "Sync can delete files that exist only at the remote destination. To continue, type exactly:\n{phrase}",
        "sync_phrase": "SYNC {target}",
        "error_title": "Storage",
        "remotes_found": "{count} configured remote(s)",
        "auto_start": "Sorting completed successfully; starting automatic cloud copy.",
        "log_title": "rclone activity",
    },
    "ar": {
        "tab": "التخزين",
        "title": "التخزين السحابي · rclone",
        "hint": "تظل المعالجة وبيانات الاستكمال محلية، ثم يتم نسخ النتائج المكتملة إلى أي remote مُعد في rclone. الرفع التلقائي يستخدم النسخ فقط ولا يحذف ملفات من السحابة.",
        "binary": "حالة rclone",
        "not_checked": "لم يتم الفحص بعد",
        "not_found": "rclone غير متاح",
        "remote": "الـ remote المُعد",
        "remote_path": "المجلد الأساسي على السحابة",
        "local_output": "مجلد النتائج المحلي",
        "mode": "وضع النقل اليدوي",
        "copy": "نسخ · آمن ولا يحذف ملفات من السحابة",
        "sync": "مزامنة مرآة · قد تحذف الملفات الزائدة على السحابة",
        "auto": "نسخ النتائج تلقائيًا بعد نجاح عملية الترتيب",
        "auto_hint": "الوضع التلقائي يستخدم rclone copy دائمًا حتى لو كان الوضع اليدوي Sync.",
        "bandwidth": "حد سرعة الرفع (اختياري، مثال 10M)",
        "transfers": "عدد عمليات النقل المتوازية",
        "checkers": "عدد عمليات الفحص المتوازية",
        "refresh": "تحديث الـ remotes",
        "test": "اختبار الاتصال",
        "preview": "معاينة بدون تنفيذ",
        "upload": "رفع الآن",
        "cancel": "إلغاء النقل",
        "idle": "التخزين في وضع الاستعداد",
        "checking": "جارٍ فحص rclone…",
        "testing": "جارٍ اختبار الـ remote…",
        "running_copy": "جارٍ نسخ النتائج إلى السحابة…",
        "running_sync": "جارٍ مزامنة المرآة…",
        "running_preview": "جارٍ معاينة النقل…",
        "success": "اكتمل نقل الملفات بنجاح",
        "preview_done": "اكتملت المعاينة بدون تنفيذ",
        "failed": "فشل نقل الملفات",
        "cancelled": "تم إلغاء نقل الملفات",
        "choose_remote": "اختر remote مُعد في rclone أولًا.",
        "choose_output": "اختر مجلد نتائج محلي صالح أولًا.",
        "sync_title": "تأكيد المزامنة التي قد تحذف ملفات",
        "sync_prompt": "قد يحذف Sync الملفات الموجودة فقط في وجهة السحابة. للمتابعة اكتب النص التالي كما هو:\n{phrase}",
        "sync_phrase": "SYNC {target}",
        "error_title": "التخزين",
        "remotes_found": "تم العثور على {count} remote",
        "auto_start": "اكتملت عملية الترتيب بنجاح؛ سيبدأ النسخ التلقائي إلى السحابة.",
        "log_title": "نشاط rclone",
    },
    "zh": {
        "tab": "存储",
        "title": "云存储 · rclone",
        "hint": "处理和断点恢复数据保留在本地，任务完成后再复制到任意已配置的 rclone 远程。自动上传始终使用 copy，不会删除远程文件。",
        "binary": "rclone 状态",
        "not_checked": "尚未检查",
        "not_found": "rclone 不可用",
        "remote": "已配置远程",
        "remote_path": "远程基础文件夹",
        "local_output": "本地输出",
        "mode": "手动传输模式",
        "copy": "复制 · 安全，不删除远程文件",
        "sync": "镜像同步 · 可能删除远程多余文件",
        "auto": "排序成功后自动复制输出",
        "auto_hint": "即使手动模式选择 Sync，自动模式也始终使用 rclone copy。",
        "bandwidth": "带宽限制（可选，例如 10M）",
        "transfers": "并行传输数",
        "checkers": "并行检查数",
        "refresh": "刷新远程",
        "test": "测试远程",
        "preview": "空运行预览",
        "upload": "立即上传",
        "cancel": "取消传输",
        "idle": "存储空闲",
        "checking": "正在检查 rclone…",
        "testing": "正在测试远程…",
        "running_copy": "正在复制输出到云端…",
        "running_sync": "正在同步镜像…",
        "running_preview": "正在预览传输…",
        "success": "存储传输完成",
        "preview_done": "空运行预览完成",
        "failed": "存储传输失败",
        "cancelled": "存储传输已取消",
        "choose_remote": "请先选择已配置的 rclone 远程。",
        "choose_output": "请先选择有效的本地输出文件夹。",
        "sync_title": "确认破坏性镜像",
        "sync_prompt": "Sync 可能删除仅存在于远程目标中的文件。若要继续，请准确输入：\n{phrase}",
        "sync_phrase": "SYNC {target}",
        "error_title": "存储",
        "remotes_found": "找到 {count} 个已配置远程",
        "auto_start": "排序成功完成；正在启动自动云端复制。",
        "log_title": "rclone 活动",
    },
}


def apply_rclone_gui(module: Any) -> None:
    """Add a non-MCP Storage Center to the desktop application."""
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_collect = module.App.collect
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self._sorter_was_running = False
        self.rclone_process = None
        self.rclone_busy = False

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=18)
        self.main_tabs.add(page, text="Storage")
        self.rclone_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=16)
        header.pack(fill="x", pady=(0, 12))
        self.rclone_title = module.ttk.Label(header, style="Metric.TLabel")
        self.rclone_title.pack(anchor="w")
        self.rclone_hint = module.ttk.Label(
            header, style="MetricName.TLabel", wraplength=980, justify="left"
        )
        self.rclone_hint.pack(anchor="w", pady=(5, 0))

        form = module.ttk.Frame(page, style="Panel.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self.vars["rclone_remote"] = module.tk.StringVar()
        self.vars["rclone_path"] = module.tk.StringVar(value="CatalogMesh")
        self.vars["rclone_mode"] = module.tk.StringVar(value="copy")
        self.vars["rclone_auto"] = module.tk.BooleanVar(value=False)
        self.vars["rclone_bwlimit"] = module.tk.StringVar()
        self.vars["rclone_transfers"] = module.tk.StringVar(value="4")
        self.vars["rclone_checkers"] = module.tk.StringVar(value="8")
        self.rclone_status = module.tk.StringVar(value="")
        self.rclone_binary_status = module.tk.StringVar(value="")

        def row_label(row):
            label = module.ttk.Label(form, style="Panel.TLabel")
            label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)
            return label

        self.rclone_binary_label = row_label(0)
        module.ttk.Label(form, textvariable=self.rclone_binary_status, style="MetricName.TLabel").grid(
            row=0, column=1, sticky="w", pady=6
        )
        self.rclone_remote_label = row_label(1)
        self.rclone_remote_box = module.ttk.Combobox(
            form, textvariable=self.vars["rclone_remote"], state="readonly"
        )
        self.rclone_remote_box.grid(row=1, column=1, sticky="ew", pady=6)
        self.rclone_refresh_button = module.ttk.Button(
            form, style="Soft.TButton", command=self.refresh_rclone_remotes
        )
        self.rclone_refresh_button.grid(row=1, column=2, padx=(8, 0), pady=6)

        self.rclone_path_label = row_label(2)
        module.ttk.Entry(form, textvariable=self.vars["rclone_path"]).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=6
        )
        self.rclone_output_label = row_label(3)
        self.rclone_output_value = module.ttk.Label(
            form, textvariable=self.vars["output"], style="MetricName.TLabel", wraplength=780
        )
        self.rclone_output_value.grid(row=3, column=1, columnspan=2, sticky="w", pady=6)

        self.rclone_mode_label = row_label(4)
        mode_frame = module.ttk.Frame(form, style="Panel.TFrame")
        mode_frame.grid(row=4, column=1, columnspan=2, sticky="w", pady=6)
        self.rclone_copy_radio = module.ttk.Radiobutton(
            mode_frame, variable=self.vars["rclone_mode"], value="copy"
        )
        self.rclone_copy_radio.pack(side="left", padx=(0, 16))
        self.rclone_sync_radio = module.ttk.Radiobutton(
            mode_frame, variable=self.vars["rclone_mode"], value="sync"
        )
        self.rclone_sync_radio.pack(side="left")

        self.rclone_bw_label = row_label(5)
        module.ttk.Entry(form, textvariable=self.vars["rclone_bwlimit"], width=18).grid(
            row=5, column=1, sticky="w", pady=6
        )

        parallel = module.ttk.Frame(form, style="Panel.TFrame")
        parallel.grid(row=6, column=0, columnspan=3, sticky="ew", pady=6)
        self.rclone_transfers_label = module.ttk.Label(parallel, style="Panel.TLabel")
        self.rclone_transfers_label.pack(side="left")
        module.ttk.Spinbox(
            parallel, from_=1, to=32, textvariable=self.vars["rclone_transfers"], width=5
        ).pack(side="left", padx=(8, 22))
        self.rclone_checkers_label = module.ttk.Label(parallel, style="Panel.TLabel")
        self.rclone_checkers_label.pack(side="left")
        module.ttk.Spinbox(
            parallel, from_=1, to=64, textvariable=self.vars["rclone_checkers"], width=5
        ).pack(side="left", padx=(8, 0))

        auto_card = module.ttk.Frame(page, style="Card.TFrame", padding=14)
        auto_card.pack(fill="x", pady=(10, 10))
        self.rclone_auto_check = module.ttk.Checkbutton(
            auto_card, variable=self.vars["rclone_auto"], style="Card.TCheckbutton"
        )
        self.rclone_auto_check.pack(anchor="w")
        self.rclone_auto_hint = module.ttk.Label(
            auto_card, style="MetricName.TLabel", wraplength=960
        )
        self.rclone_auto_hint.pack(anchor="w", pady=(4, 0))

        actions = module.ttk.Frame(page, style="Panel.TFrame")
        actions.pack(fill="x", pady=(2, 10))
        self.rclone_test_button = module.ttk.Button(
            actions, style="Soft.TButton", command=self.test_rclone_remote
        )
        self.rclone_test_button.pack(side="left", padx=(0, 7))
        self.rclone_preview_button = module.ttk.Button(
            actions, style="Soft.TButton", command=lambda: self.start_rclone_transfer(dry_run=True)
        )
        self.rclone_preview_button.pack(side="left", padx=(0, 7))
        self.rclone_upload_button = module.ttk.Button(
            actions, style="Accent.TButton", command=lambda: self.start_rclone_transfer(dry_run=False)
        )
        self.rclone_upload_button.pack(side="left", padx=(0, 7))
        self.rclone_cancel_button = module.ttk.Button(
            actions, style="Danger.TButton", command=self.cancel_rclone_transfer
        )
        self.rclone_cancel_button.pack(side="left", padx=(0, 7))
        module.ttk.Label(actions, textvariable=self.rclone_status, style="Panel.TLabel").pack(side="right")

        log_card = module.ttk.Frame(page, style="Card.TFrame", padding=12)
        log_card.pack(fill="both", expand=True)
        self.rclone_log_label = module.ttk.Label(log_card, style="MetricName.TLabel")
        self.rclone_log_label.pack(anchor="w", pady=(0, 6))
        log_frame = module.ttk.Frame(log_card, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True)
        self.rclone_log = module.tk.Text(
            log_frame,
            height=10,
            wrap="word",
            bg=self.colors["log"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            borderwidth=0,
        )
        scrollbar = module.ttk.Scrollbar(log_frame, orient="vertical", command=self.rclone_log.yview)
        self.rclone_log.configure(yscrollcommand=scrollbar.set, state="disabled")
        self.rclone_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.root.after(200, self.refresh_rclone_remotes)

    def append_rclone_log(self, line):
        if not hasattr(self, "rclone_log"):
            return
        self.rclone_log.configure(state="normal")
        self.rclone_log.insert("end", str(line) + "\n")
        self.rclone_log.see("end")
        self.rclone_log.configure(state="disabled")

    def set_rclone_busy(self, busy):
        self.rclone_busy = bool(busy)
        state = "disabled" if busy else "normal"
        for widget_name in (
            "rclone_refresh_button", "rclone_test_button", "rclone_preview_button", "rclone_upload_button"
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.configure(state=state)
        if hasattr(self, "rclone_cancel_button"):
            self.rclone_cancel_button.configure(state="normal" if busy else "disabled")

    def refresh_rclone_remotes(self):
        if self.rclone_busy:
            return
        self.rclone_status.set(text(self)["checking"])
        self.rclone_binary_status.set(text(self)["checking"])

        def worker():
            try:
                version = rclone_version()
                remotes = list_remotes()
                error = None
            except (RcloneError, OSError, ValueError, subprocess.SubprocessError) as exc:
                version, remotes, error = "", (), str(exc)

            def finish():
                if error:
                    self.rclone_binary_status.set(text(self)["not_found"])
                    self.rclone_status.set(text(self)["idle"])
                    self.append_rclone_log(error)
                    return
                self.rclone_binary_status.set(version)
                self.rclone_remote_box.configure(values=remotes)
                current = self.vars["rclone_remote"].get()
                if current not in remotes:
                    self.vars["rclone_remote"].set(remotes[0] if remotes else "")
                self.rclone_status.set(text(self)["remotes_found"].format(count=len(remotes)))

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def current_rclone_target(self):
        remote = self.vars["rclone_remote"].get()
        if not remote:
            raise ValueError(text(self)["choose_remote"])
        base = self.vars["rclone_path"].get()
        output_raw = self.vars["output"].get().strip()
        output = Path(output_raw).expanduser() if output_raw else None
        if output is None or not output.is_dir():
            raise ValueError(text(self)["choose_output"])
        # Preserve the local output folder as one cloud directory so separate
        # workspaces cannot silently overwrite one another.
        subpath = "/".join(part for part in (base.strip("/\\"), output.name) if part)
        return output, remote_target(remote, subpath)

    def test_rclone_remote(self):
        if self.rclone_busy:
            return
        try:
            _output, target = self.current_rclone_target()
        except ValueError as exc:
            module.messagebox.showerror(text(self)["error_title"], str(exc))
            return
        self.set_rclone_busy(True)
        self.rclone_status.set(text(self)["testing"])

        def worker():
            try:
                test_remote(target)
                error = None
            except (RcloneError, OSError, ValueError, subprocess.SubprocessError) as exc:
                error = str(exc)

            def finish():
                self.set_rclone_busy(False)
                if error:
                    self.rclone_status.set(text(self)["failed"])
                    self.append_rclone_log(error)
                    module.messagebox.showerror(text(self)["error_title"], error)
                else:
                    self.rclone_status.set(text(self)["success"])

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def start_rclone_transfer(self, dry_run=False, automatic=False):
        if self.rclone_busy:
            return
        try:
            output, target = self.current_rclone_target()
            mode = "copy" if automatic else self.vars["rclone_mode"].get().strip().lower()
            options = TransferOptions(
                mode=mode,
                dry_run=bool(dry_run),
                transfers=int(self.vars["rclone_transfers"].get() or "4"),
                checkers=int(self.vars["rclone_checkers"].get() or "8"),
                bwlimit=self.vars["rclone_bwlimit"].get(),
            ).validated()
        except (ValueError, RcloneError) as exc:
            module.messagebox.showerror(text(self)["error_title"], str(exc))
            return

        if options.mode == "sync" and not options.dry_run:
            phrase = text(self)["sync_phrase"].format(target=target)
            entered = module.simpledialog.askstring(
                text(self)["sync_title"],
                text(self)["sync_prompt"].format(phrase=phrase),
                parent=self.root,
            )
            if entered != phrase:
                return

        self.set_rclone_busy(True)
        status_key = "running_preview" if options.dry_run else (
            "running_sync" if options.mode == "sync" else "running_copy"
        )
        self.rclone_status.set(text(self)[status_key])
        self.append_rclone_log(f"{options.mode.upper()} {output} -> {target}" + (" [DRY-RUN]" if options.dry_run else ""))

        def on_line(line):
            self.root.after(0, lambda value=line: self.append_rclone_log(value))

        def on_process(process):
            self.rclone_process = process

        def worker():
            try:
                code = stream_transfer(output, target, options=options, on_line=on_line, on_process=on_process)
                error = None
            except (RcloneError, OSError, ValueError, subprocess.SubprocessError) as exc:
                code, error = -1, str(exc)
            try:
                append_sync_audit(
                    output,
                    target=target,
                    mode=options.mode,
                    dry_run=options.dry_run,
                    returncode=code,
                    automatic=automatic,
                )
            except OSError:
                pass

            def finish():
                self.rclone_process = None
                self.set_rclone_busy(False)
                if error:
                    self.append_rclone_log(error)
                    self.rclone_status.set(text(self)["failed"])
                    module.messagebox.showerror(text(self)["error_title"], error)
                elif code == 0:
                    self.rclone_status.set(text(self)["preview_done"] if options.dry_run else text(self)["success"])
                else:
                    self.rclone_status.set(text(self)["cancelled"] if code < 0 else text(self)["failed"])

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def cancel_rclone_transfer(self):
        process = getattr(self, "rclone_process", None)
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            pass
        self.rclone_status.set(text(self)["cancelled"])

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "rclone_page"):
            return
        t = text(self)
        self.main_tabs.tab(self.rclone_page, text=t["tab"])
        self.rclone_title.configure(text=t["title"])
        self.rclone_hint.configure(text=t["hint"])
        self.rclone_binary_label.configure(text=t["binary"])
        self.rclone_remote_label.configure(text=t["remote"])
        self.rclone_path_label.configure(text=t["remote_path"])
        self.rclone_output_label.configure(text=t["local_output"])
        self.rclone_mode_label.configure(text=t["mode"])
        self.rclone_copy_radio.configure(text=t["copy"])
        self.rclone_sync_radio.configure(text=t["sync"])
        self.rclone_auto_check.configure(text=t["auto"])
        self.rclone_auto_hint.configure(text=t["auto_hint"])
        self.rclone_bw_label.configure(text=t["bandwidth"])
        self.rclone_transfers_label.configure(text=t["transfers"])
        self.rclone_checkers_label.configure(text=t["checkers"])
        self.rclone_refresh_button.configure(text=t["refresh"])
        self.rclone_test_button.configure(text=t["test"])
        self.rclone_preview_button.configure(text=t["preview"])
        self.rclone_upload_button.configure(text=t["upload"])
        self.rclone_cancel_button.configure(text=t["cancel"])
        self.rclone_log_label.configure(text=t["log_title"])
        if not self.rclone_status.get():
            self.rclone_status.set(t["idle"])
        if not self.rclone_binary_status.get():
            self.rclone_binary_status.set(t["not_checked"])

    def load_values(self):
        base_load_values(self)
        if "rclone_remote" not in self.vars:
            return
        self.vars["rclone_remote"].set(self.values.get("PRODUCT_SORTER_RCLONE_REMOTE", ""))
        self.vars["rclone_path"].set(self.values.get("PRODUCT_SORTER_RCLONE_PATH", "CatalogMesh"))
        self.vars["rclone_mode"].set(self.values.get("PRODUCT_SORTER_RCLONE_MODE", "copy") if self.values.get("PRODUCT_SORTER_RCLONE_MODE") in {"copy", "sync"} else "copy")
        self.vars["rclone_auto"].set(str(self.values.get("PRODUCT_SORTER_RCLONE_AUTO_COPY", "")).lower() in {"1", "true", "yes", "on"})
        self.vars["rclone_bwlimit"].set(self.values.get("PRODUCT_SORTER_RCLONE_BWLIMIT", ""))
        self.vars["rclone_transfers"].set(self.values.get("PRODUCT_SORTER_RCLONE_TRANSFERS", "4"))
        self.vars["rclone_checkers"].set(self.values.get("PRODUCT_SORTER_RCLONE_CHECKERS", "8"))

    def collect(self):
        values = base_collect(self)
        if "rclone_remote" in self.vars:
            values.update({
                "PRODUCT_SORTER_RCLONE_REMOTE": self.vars["rclone_remote"].get(),
                "PRODUCT_SORTER_RCLONE_PATH": self.vars["rclone_path"].get(),
                "PRODUCT_SORTER_RCLONE_MODE": self.vars["rclone_mode"].get(),
                "PRODUCT_SORTER_RCLONE_AUTO_COPY": "true" if self.vars["rclone_auto"].get() else "false",
                "PRODUCT_SORTER_RCLONE_BWLIMIT": self.vars["rclone_bwlimit"].get(),
                "PRODUCT_SORTER_RCLONE_TRANSFERS": self.vars["rclone_transfers"].get(),
                "PRODUCT_SORTER_RCLONE_CHECKERS": self.vars["rclone_checkers"].get(),
            })
        return values

    def set_running(self, running):
        previous = bool(getattr(self, "_sorter_was_running", False))
        base_set_running(self, running)
        self._sorter_was_running = bool(running)
        if previous and not running:
            process = getattr(self, "p", None)
            succeeded = process is not None and process.poll() == 0
            auto = "rclone_auto" in self.vars and bool(self.vars["rclone_auto"].get())
            if succeeded and auto:
                self.append_rclone_log(text(self)["auto_start"])
                self.root.after(100, lambda: self.start_rclone_transfer(dry_run=False, automatic=True))

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.collect = collect
    module.App.set_running = set_running
    module.App.refresh_rclone_remotes = refresh_rclone_remotes
    module.App.current_rclone_target = current_rclone_target
    module.App.test_rclone_remote = test_rclone_remote
    module.App.start_rclone_transfer = start_rclone_transfer
    module.App.cancel_rclone_transfer = cancel_rclone_transfer
    module.App.append_rclone_log = append_rclone_log
    module.App.set_rclone_busy = set_rclone_busy
