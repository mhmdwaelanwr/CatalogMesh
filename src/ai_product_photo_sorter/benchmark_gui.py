"""GUI extension for the Product Sorter Benchmark Center."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_TEXT = {
    "en": {
        "tab": "Benchmark",
        "title": "Benchmark Center",
        "hint": "Measure the real sorter pipeline in an isolated run using the current provider priority, model and API settings.",
        "count": "Benchmark photo count",
        "start": "Start benchmark",
        "open": "Open latest report",
        "idle": "No benchmark report yet.",
        "elapsed": "Elapsed",
        "running": "Benchmark running",
    },
    "ar": {
        "tab": "القياس",
        "title": "مركز قياس الأداء",
        "hint": "يقيس نفس مسار المعالجة الحقيقي في تشغيل معزول باستخدام ترتيب المزودات والموديلات ومفاتيح API الحالية.",
        "count": "عدد صور الاختبار",
        "start": "ابدأ Benchmark",
        "open": "افتح آخر تقرير",
        "idle": "لا يوجد تقرير Benchmark حتى الآن.",
        "elapsed": "الوقت المنقضي",
        "running": "Benchmark يعمل الآن",
    },
    "zh": {
        "tab": "基准",
        "title": "基准测试中心",
        "hint": "使用当前提供商优先级、模型和 API 设置，在隔离运行中测量真实处理流水线。",
        "count": "测试图片数量",
        "start": "开始基准测试",
        "open": "打开最新报告",
        "idle": "尚无基准测试报告。",
        "elapsed": "已用时间",
        "running": "基准测试运行中",
    },
}


def _remove_option(cmd: list[str], name: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(cmd):
        if cmd[index] == name:
            index += 2
            continue
        result.append(cmd[index])
        index += 1
    return result


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _result_summary(result: dict[str, Any]) -> str:
    completed = int(result.get("photos_completed") or 0)
    selected = int(result.get("photos_selected") or 0)
    calls = int(result.get("logical_provider_calls") or 0)
    wall = float(result.get("wall_seconds") or 0.0)
    return_code = result.get("return_code")
    if return_code not in (0, None) or (selected and completed == 0):
        return (
            f"Benchmark failed before useful measurement · exit {return_code} · "
            f"{completed}/{selected} photos · {calls} provider calls · {_format_elapsed(wall)}"
        )
    throughput = float(result.get("photos_per_second") or 0.0)
    per_photo = result.get("seconds_per_photo")
    per_photo_text = f"{float(per_photo):.3f} s/photo" if per_photo is not None else "n/a"
    return (
        f"Completed · {completed}/{selected} photos · {_format_elapsed(wall)} · "
        f"{throughput:.4f} photos/s · {per_photo_text} · {calls} provider calls"
    )


def apply_benchmark_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_collect = module.App.collect
    base_command = module.App.command
    base_start = module.App.start
    base_set_running = module.App.set_running
    base_append_log = module.App.append_log

    def build(self):
        base_build(self)
        self._benchmark_mode = False
        self._benchmark_launching = False
        self._benchmark_started_monotonic: float | None = None
        self.latest_benchmark_report: Path | None = None
        self.vars["benchmark_sample"] = module.tk.StringVar(value="50")
        self.benchmark_status = module.tk.StringVar(value="")
        self.benchmark_elapsed = module.tk.StringVar(value="00:00:00")

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=22)
        self.main_tabs.insert(3, page, text="Benchmark")
        self.benchmark_page = page

        card = module.ttk.Frame(page, style="Card.TFrame", padding=20)
        card.pack(fill="x", anchor="n")
        self.benchmark_title = module.ttk.Label(card, style="Metric.TLabel")
        self.benchmark_title.pack(anchor="w")
        self.benchmark_hint = module.ttk.Label(card, style="MetricName.TLabel", wraplength=900)
        self.benchmark_hint.pack(anchor="w", pady=(5, 18))

        row = module.ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        self.benchmark_count_label = module.ttk.Label(row, style="MetricName.TLabel")
        self.benchmark_count_label.pack(side="left", padx=(0, 8))
        module.ttk.Entry(row, textvariable=self.vars["benchmark_sample"], width=10).pack(side="left", padx=(0, 12))
        self.benchmark_start_button = module.ttk.Button(row, style="Accent.TButton", command=self.start_benchmark)
        self.benchmark_start_button.pack(side="left", padx=(0, 8))
        self.benchmark_open_button = module.ttk.Button(row, style="Soft.TButton", command=self.open_latest_benchmark)
        self.benchmark_open_button.pack(side="left")

        metric_row = module.ttk.Frame(card, style="Card.TFrame")
        metric_row.pack(fill="x", pady=(18, 0))
        elapsed_card = module.ttk.Frame(metric_row, style="Card.TFrame")
        elapsed_card.pack(side="left", padx=(0, 24))
        self.benchmark_elapsed_label = module.ttk.Label(elapsed_card, style="MetricName.TLabel")
        self.benchmark_elapsed_label.pack(anchor="w")
        module.ttk.Label(elapsed_card, textvariable=self.benchmark_elapsed, style="Metric.TLabel").pack(anchor="w")

        module.ttk.Label(card, textvariable=self.benchmark_status, style="MetricName.TLabel", wraplength=900).pack(anchor="w", pady=(12, 0))

    def apply_language(self):
        base_apply_language(self)
        text = _TEXT.get(self.lang, _TEXT["en"])
        if hasattr(self, "benchmark_page"):
            self.main_tabs.tab(3, text=text["tab"])
            if len(self.main_tabs.tabs()) > 4:
                self.main_tabs.tab(4, text=self.t("about"))
            self.benchmark_title.config(text=text["title"])
            self.benchmark_hint.config(text=text["hint"])
            self.benchmark_count_label.config(text=text["count"])
            self.benchmark_start_button.config(text=text["start"])
            self.benchmark_open_button.config(text=text["open"])
            self.benchmark_elapsed_label.config(text=text["elapsed"])
            if not self.benchmark_status.get():
                self.benchmark_status.set(text["idle"])

    def load_values(self):
        base_load_values(self)
        if "benchmark_sample" in self.vars:
            self.vars["benchmark_sample"].set(self.values.get("BENCHMARK_LIMIT", "50") or "50")

    def collect(self):
        values = base_collect(self)
        if "benchmark_sample" in self.vars:
            values["BENCHMARK_LIMIT"] = self.vars["benchmark_sample"].get().strip()
        return values

    def command(self):
        cmd = base_command(self)
        if not getattr(self, "_benchmark_mode", False):
            return cmd
        cmd = _remove_option(cmd, "--limit")
        count = self.vars["benchmark_sample"].get().strip()
        if count:
            cmd += ["--limit", count]
        cmd += ["--benchmark"]
        return cmd

    def start(self):
        if not getattr(self, "_benchmark_launching", False):
            self._benchmark_mode = False
        return base_start(self)

    def _tick_benchmark_elapsed(self):
        started = getattr(self, "_benchmark_started_monotonic", None)
        if started is None:
            return
        self.benchmark_elapsed.set(_format_elapsed(time.monotonic() - started))
        if self.p and self.p.poll() is None and getattr(self, "_benchmark_mode", False):
            self.root.after(250, self._tick_benchmark_elapsed)

    def start_benchmark(self):
        raw = self.vars["benchmark_sample"].get().strip()
        if raw:
            try:
                count = int(raw)
                if count <= 0:
                    raise ValueError
            except ValueError:
                module.messagebox.showerror("Benchmark", "Benchmark photo count must be a positive integer.")
                return
        self._benchmark_launching = True
        self._benchmark_mode = True
        self._benchmark_started_monotonic = time.monotonic()
        self.benchmark_elapsed.set("00:00:00")
        try:
            self.start()
        finally:
            self._benchmark_launching = False
        if self.p and self.p.poll() is None:
            self.main_tabs.select(3)
            self.benchmark_status.set(_TEXT.get(self.lang, _TEXT["en"])["running"] + "…")
            self._tick_benchmark_elapsed()
        else:
            self._benchmark_started_monotonic = None

    def append_log(self, line):
        base_append_log(self, line)
        prefix = "Benchmark report: "
        if line.startswith(prefix):
            path = Path(line[len(prefix):].strip())
            self.latest_benchmark_report = path
            json_path = path.with_name("benchmark.json")
            try:
                result = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                result = None
            if isinstance(result, dict):
                self.benchmark_status.set(_result_summary(result))
                self.benchmark_elapsed.set(_format_elapsed(float(result.get("wall_seconds") or 0.0)))
            else:
                self.benchmark_status.set(str(path))
            self._benchmark_started_monotonic = None
            if hasattr(self, "benchmark_open_button"):
                self.benchmark_open_button.config(state="normal")

    def open_latest_benchmark(self):
        path = self.latest_benchmark_report
        if path is None:
            output = self.vars["output"].get().strip()
            latest = Path(output) / "benchmarks" / "latest.txt" if output else None
            if latest and latest.is_file():
                try:
                    path = Path(latest.read_text(encoding="utf-8").strip())
                except OSError:
                    path = None
        if not path or not path.exists():
            module.messagebox.showinfo("Benchmark", _TEXT.get(self.lang, _TEXT["en"])["idle"])
            return
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "benchmark_start_button"):
            self.benchmark_start_button.config(state="disabled" if running else "normal")

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.collect = collect
    module.App.command = command
    module.App.start = start
    module.App.start_benchmark = start_benchmark
    module.App._tick_benchmark_elapsed = _tick_benchmark_elapsed
    module.App.append_log = append_log
    module.App.open_latest_benchmark = open_latest_benchmark
    module.App.set_running = set_running
