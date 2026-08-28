"""In-app report browser with a GitHub-inspired native Markdown preview."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .report_preview import discover_reports, markdown_blocks, read_report_text, report_kind

_INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))")
_LINK = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)$")

_TEXT = {
    "en": {
        "tab": "Reports",
        "title": "Report Center",
        "hint": "Browse operation and benchmark evidence without leaving Product Sorter. Markdown reports use a GitHub-inspired rendered preview.",
        "refresh": "Refresh",
        "preview": "Preview",
        "raw": "Raw",
        "copy": "Copy",
        "external": "Open externally",
        "reports": "REPORTS",
        "type": "Type",
        "name": "Report",
        "modified": "Modified",
        "empty": "No report artifacts found for the selected output folder.",
        "copied": "Report copied to clipboard",
    },
    "ar": {
        "tab": "Reports",
        "title": "مركز التقارير",
        "hint": "راجع تقارير التشغيل والـBenchmark من داخل Product Sorter. ملفات Markdown تظهر بمعاينة منسقة شبيهة بـGitHub.",
        "refresh": "تحديث",
        "preview": "معاينة",
        "raw": "النص الخام",
        "copy": "نسخ",
        "external": "فتح خارجي",
        "reports": "التقارير",
        "type": "النوع",
        "name": "التقرير",
        "modified": "آخر تعديل",
        "empty": "لا توجد تقارير في مجلد الإخراج المحدد.",
        "copied": "تم نسخ التقرير",
    },
    "zh": {
        "tab": "Reports",
        "title": "报告中心",
        "hint": "无需离开 Product Sorter 即可查看任务和基准测试证据。Markdown 报告使用类似 GitHub 的格式化预览。",
        "refresh": "刷新",
        "preview": "预览",
        "raw": "原始文本",
        "copy": "复制",
        "external": "外部打开",
        "reports": "报告",
        "type": "类型",
        "name": "报告",
        "modified": "修改时间",
        "empty": "所选输出文件夹中没有报告文件。",
        "copied": "报告已复制",
    },
}


def _modified_text(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


def _relative_report_name(output: str, path: Path) -> str:
    try:
        if output:
            return path.relative_to(Path(output).expanduser()).as_posix()
    except (OSError, ValueError):
        pass
    return path.name


def _selected_report_path(owner: Any) -> Path | None:
    """Resolve a user selection while suppressing refresh-generated events."""
    if getattr(owner, "_report_refreshing", False):
        return None
    selected = owner.report_tree.selection()
    if not selected:
        return None
    path = owner.report_paths.get(selected[0])
    if path == getattr(owner, "current_report_path", None):
        return None
    return path


# Kept as a small public seam for the headless regression test. Tk widgets
# themselves cannot be constructed reliably on every CI runner.
_select_report_for_test = _selected_report_path


def apply_report_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_toggle_theme = module.App.toggle_theme
    base_append_log = module.App.append_log
    base_open_latest_benchmark = getattr(module.App, "open_latest_benchmark", None)

    def _text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        self.report_mode = module.tk.StringVar(value="preview")
        self.report_status = module.tk.StringVar(value="")
        self.current_report_path: Path | None = None
        self.current_report_text = ""
        self.report_paths: dict[str, Path] = {}
        self._report_refreshing = False

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=20)
        self.main_tabs.insert(5, page, text="Reports")
        self.report_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        header.pack(fill="x", pady=(0, 12))
        self.report_title = module.ttk.Label(header, style="Metric.TLabel")
        self.report_title.pack(anchor="w")
        self.report_hint = module.ttk.Label(header, style="MetricName.TLabel", wraplength=950)
        self.report_hint.pack(anchor="w", pady=(4, 12))

        actions = module.ttk.Frame(header, style="Card.TFrame")
        actions.pack(fill="x")
        self.report_refresh_button = module.ttk.Button(actions, style="Soft.TButton", command=self.refresh_reports)
        self.report_refresh_button.pack(side="left", padx=(0, 7))
        self.report_preview_button = module.ttk.Button(actions, style="Accent.TButton", command=lambda: self.set_report_mode("preview"))
        self.report_preview_button.pack(side="left", padx=(0, 7))
        self.report_raw_button = module.ttk.Button(actions, style="Soft.TButton", command=lambda: self.set_report_mode("raw"))
        self.report_raw_button.pack(side="left", padx=(0, 7))
        self.report_copy_button = module.ttk.Button(actions, style="Soft.TButton", command=self.copy_report)
        self.report_copy_button.pack(side="left", padx=(0, 7))
        self.report_external_button = module.ttk.Button(actions, style="Soft.TButton", command=self.open_report_external)
        self.report_external_button.pack(side="left")
        module.ttk.Label(actions, textvariable=self.report_status, style="MetricName.TLabel").pack(side="right")

        paned = module.ttk.Panedwindow(page, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = module.ttk.Frame(paned, style="Card.TFrame", padding=12)
        right = module.ttk.Frame(paned, style="Card.TFrame", padding=12)
        paned.add(left, weight=2)
        paned.add(right, weight=5)

        self.report_list_label = module.ttk.Label(left, style="Section.TLabel")
        self.report_list_label.pack(anchor="w", pady=(0, 8))
        self.report_tree = module.ttk.Treeview(
            left,
            columns=("type", "name", "modified"),
            show="headings",
            selectmode="browse",
        )
        self.report_tree.column("type", width=90, anchor="w")
        self.report_tree.column("name", width=300, anchor="w")
        self.report_tree.column("modified", width=135, anchor="w")
        self.report_tree.pack(fill="both", expand=True)
        self.report_tree.bind("<<TreeviewSelect>>", self.select_report)

        viewer_frame = module.ttk.Frame(right, style="Card.TFrame")
        viewer_frame.pack(fill="both", expand=True)
        self.report_viewer = module.tk.Text(
            viewer_frame,
            wrap="word",
            borderwidth=0,
            padx=22,
            pady=18,
            undo=False,
        )
        scroll = module.ttk.Scrollbar(viewer_frame, orient="vertical", command=self.report_viewer.yview)
        self.report_viewer.configure(yscrollcommand=scroll.set)
        self.report_viewer.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.report_viewer.config(state="disabled")

        self.refresh_reports()

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "report_page"):
            return
        text = _text(self)
        self.main_tabs.tab(5, text=text["tab"])
        if len(self.main_tabs.tabs()) > 6:
            self.main_tabs.tab(6, text=self.t("about"))
        self.report_title.config(text=text["title"])
        self.report_hint.config(text=text["hint"])
        self.report_refresh_button.config(text=text["refresh"])
        self.report_preview_button.config(text=text["preview"])
        self.report_raw_button.config(text=text["raw"])
        self.report_copy_button.config(text=text["copy"])
        self.report_external_button.config(text=text["external"])
        self.report_list_label.config(text=text["reports"])
        self.report_tree.heading("type", text=text["type"])
        self.report_tree.heading("name", text=text["name"])
        self.report_tree.heading("modified", text=text["modified"])
        if not self.report_paths:
            self.report_status.set(text["empty"])

    def refresh_reports(self):
        if not hasattr(self, "report_tree"):
            return
        output = self.vars.get("output").get().strip() if "output" in self.vars else ""
        paths = discover_reports(output)
        current = self.current_report_path
        if current and current.is_file() and current not in paths:
            paths.insert(0, current)
        self._report_refreshing = True
        try:
            self.report_tree.delete(*self.report_tree.get_children())
            self.report_paths = {}
            selected_iid = None
            for index, path in enumerate(paths):
                iid = f"report-{index}"
                self.report_paths[iid] = path
                self.report_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(report_kind(path), _relative_report_name(output, path), _modified_text(path)),
                )
                if current and path == current:
                    selected_iid = iid
            if selected_iid:
                self.report_tree.selection_set(selected_iid)
                self.report_tree.see(selected_iid)
        finally:
            self._report_refreshing = False
        if paths:
            self.report_status.set(f"{len(paths)} report artifact{'s' if len(paths) != 1 else ''}")
        else:
            self.report_status.set(_text(self)["empty"])

    def select_report(self, event=None):
        path = _selected_report_path(self)
        if path:
            self.show_report(path, select_tab=False)

    def show_report(self, path: Path | str, select_tab: bool = True):
        path = Path(path)
        try:
            text = read_report_text(path)
        except (OSError, ValueError) as exc:
            module.messagebox.showerror("Reports", str(exc))
            return
        self.current_report_path = path
        self.current_report_text = text
        if select_tab:
            self.main_tabs.select(5)
        # Do not rebuild/reselect the Treeview here. Re-selection emits another
        # <<TreeviewSelect>> event on Tk and previously caused an infinite
        # select -> show -> refresh loop that froze the desktop application.
        if path not in self.report_paths.values():
            self.refresh_reports()
        self.render_report()
        self.report_status.set(f"{report_kind(path)} · {path.name}")

    def set_report_mode(self, mode: str):
        self.report_mode.set("raw" if mode == "raw" else "preview")
        self.render_report()

    def _configure_report_tags(self):
        viewer = self.report_viewer
        viewer.configure(
            background=self.colors["panel2"],
            foreground=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["accent"],
        )
        viewer.tag_configure("body", font=("Sans", 10), foreground=self.colors["text"], spacing1=2, spacing3=4)
        viewer.tag_configure("h1", font=("Sans", 22, "bold"), foreground=self.colors["text"], spacing1=12, spacing3=10)
        viewer.tag_configure("h2", font=("Sans", 16, "bold"), foreground=self.colors["text"], spacing1=15, spacing3=7)
        viewer.tag_configure("h3", font=("Sans", 13, "bold"), foreground=self.colors["text"], spacing1=10, spacing3=5)
        viewer.tag_configure("h4", font=("Sans", 11, "bold"), foreground=self.colors["text"])
        viewer.tag_configure("quote", font=("Sans", 10, "italic"), foreground=self.colors["muted"], lmargin1=18, lmargin2=18, spacing1=4, spacing3=6)
        viewer.tag_configure("code", font=("Monospace", 9), foreground=self.colors["text"], background=self.colors["bg"], lmargin1=16, lmargin2=16, spacing1=5, spacing3=5)
        viewer.tag_configure("inline_code", font=("Monospace", 9), foreground=self.colors["accent"])
        viewer.tag_configure("bold", font=("Sans", 10, "bold"), foreground=self.colors["text"])
        viewer.tag_configure("link", font=("Sans", 10, "underline"), foreground=self.colors["accent"])
        viewer.tag_configure("bullet", font=("Sans", 10), foreground=self.colors["text"], lmargin1=12, lmargin2=28)
        viewer.tag_configure("table", font=("Monospace", 9), foreground=self.colors["text"], background=self.colors["panel"], lmargin1=8, lmargin2=8)
        viewer.tag_configure("table_header", font=("Monospace", 9, "bold"), foreground=self.colors["text"], background=self.colors["panel"])
        viewer.tag_configure("raw", font=("Monospace", 9), foreground=self.colors["text"])
        viewer.tag_configure("hr", foreground=self.colors["border"])

    def _insert_inline(self, text: str, base_tag: str = "body"):
        viewer = self.report_viewer
        position = 0
        for match in _INLINE.finditer(text):
            if match.start() > position:
                viewer.insert("end", text[position:match.start()], (base_tag,))
            token = match.group(0)
            if token.startswith("`"):
                viewer.insert("end", token[1:-1], (base_tag, "inline_code"))
            elif token.startswith("**"):
                viewer.insert("end", token[2:-2], (base_tag, "bold"))
            else:
                link = _LINK.match(token)
                viewer.insert("end", link.group(1) if link else token, (base_tag, "link"))
            position = match.end()
        if position < len(text):
            viewer.insert("end", text[position:], (base_tag,))

    def render_report(self):
        if not hasattr(self, "report_viewer"):
            return
        viewer = self.report_viewer
        viewer.config(state="normal")
        viewer.delete("1.0", "end")
        self._configure_report_tags()
        text = self.current_report_text
        path = self.current_report_path
        if not text or not path:
            viewer.config(state="disabled")
            return
        if self.report_mode.get() == "raw" or path.suffix.lower() != ".md":
            viewer.insert("end", text, ("raw",))
            viewer.config(state="disabled")
            return

        blocks = markdown_blocks(text)
        table_row = 0
        for block in blocks:
            kind = block["kind"]
            if kind == "blank":
                viewer.insert("end", "\n")
                table_row = 0
            elif kind == "heading":
                level = min(4, int(block.get("level", 1)))
                self._insert_inline(str(block.get("text", "")), f"h{level}")
                viewer.insert("end", "\n")
                table_row = 0
            elif kind == "quote":
                viewer.insert("end", "▌ ", ("quote",))
                self._insert_inline(str(block.get("text", "")), "quote")
                viewer.insert("end", "\n")
                table_row = 0
            elif kind == "code":
                viewer.insert("end", str(block.get("text", "")) + "\n", ("code",))
                table_row = 0
            elif kind == "bullet":
                viewer.insert("end", "• ", ("bullet",))
                self._insert_inline(str(block.get("text", "")), "bullet")
                viewer.insert("end", "\n")
                table_row = 0
            elif kind == "ordered":
                viewer.insert("end", f"{block.get('number', '')}. ", ("bullet",))
                self._insert_inline(str(block.get("text", "")), "bullet")
                viewer.insert("end", "\n")
                table_row = 0
            elif kind == "table_separator":
                continue
            elif kind == "table":
                cells = [str(cell) for cell in block.get("cells", [])]
                tag = "table_header" if table_row == 0 else "table"
                viewer.insert("end", "  │  ".join(cells) + "\n", (tag,))
                table_row += 1
            elif kind == "hr":
                viewer.insert("end", "─" * 72 + "\n", ("hr",))
                table_row = 0
            else:
                self._insert_inline(str(block.get("text", "")), "body")
                viewer.insert("end", "\n")
                table_row = 0
        viewer.config(state="disabled")

    def copy_report(self):
        if not self.current_report_text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_report_text)
        self.report_status.set(_text(self)["copied"])

    def open_report_external(self):
        path = self.current_report_path
        if not path or not path.exists():
            return
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def open_latest_benchmark(self):
        path = getattr(self, "latest_benchmark_report", None)
        if path is None:
            output = self.vars["output"].get().strip()
            latest = Path(output) / "benchmarks" / "latest.txt" if output else None
            if latest and latest.is_file():
                try:
                    path = Path(latest.read_text(encoding="utf-8").strip())
                except OSError:
                    path = None
        if path and Path(path).is_file():
            self.show_report(Path(path))
            return
        if base_open_latest_benchmark is not None:
            return base_open_latest_benchmark(self)
        module.messagebox.showinfo("Benchmark", "No benchmark report yet.")

    def append_log(self, line):
        base_append_log(self, line)
        if line.startswith("Benchmark report: ") or "SMART_REPORT.md" in line:
            if hasattr(self, "report_tree"):
                self.refresh_reports()

    def toggle_theme(self):
        base_toggle_theme(self)
        if hasattr(self, "report_viewer") and self.current_report_path:
            self.render_report()

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.refresh_reports = refresh_reports
    module.App.select_report = select_report
    module.App.show_report = show_report
    module.App.set_report_mode = set_report_mode
    module.App._configure_report_tags = _configure_report_tags
    module.App._insert_inline = _insert_inline
    module.App.render_report = render_report
    module.App.copy_report = copy_report
    module.App.open_report_external = open_report_external
    module.App.open_latest_benchmark = open_latest_benchmark
    module.App.append_log = append_log
    module.App.toggle_theme = toggle_theme
