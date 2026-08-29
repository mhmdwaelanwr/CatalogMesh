"""Desktop controls for safe, memory-aware image preprocessing."""

from __future__ import annotations

from typing import Any

from .performance_pipeline import (
    DEFAULT_CACHE_ENTRIES,
    DEFAULT_MEMORY_MB,
    DEFAULT_WORKERS,
    MAX_WORKERS,
)

_ENV_FIELDS = (
    "PRODUCT_SORTER_PREPROCESS_WORKERS",
    "PRODUCT_SORTER_PREPROCESS_MEMORY_MB",
)

_WORKER_VALUES = ("auto", "off", "1", "2", "3", "4", "6", "8", "12", "16")
_MEMORY_VALUES = ("256", "512", "768", "1024", "2048", "4096")

_TEXT = {
    "en": {
        "title": "Performance · Safe preprocessing",
        "hint": "Prepare images concurrently before each AI request while preserving provider order, grouping context, SQLite commits, and resume safety.",
        "workers": "Image-preprocess workers",
        "memory": "Memory safety budget (MiB)",
        "cache": "Encoded image-cache entries",
        "note": "Auto mode caps workers by CPU, batch size, image dimensions, and the memory budget. AI inference itself remains ordered.",
    },
    "ar": {
        "title": "الأداء · تجهيز الصور بأمان",
        "hint": "جهّز الصور بالتوازي قبل كل طلب AI مع الحفاظ على ترتيب المزود، سياق التجميع، SQLite، واستكمال العملية بعد التوقف.",
        "workers": "عدد workers لتجهيز الصور",
        "memory": "حد الذاكرة الآمن (MiB)",
        "cache": "عدد الصور المشفرة في الـcache",
        "note": "وضع Auto يحدد عدد الـworkers حسب المعالج وحجم الـbatch وأبعاد الصور وحد الذاكرة. استدعاءات الـAI نفسها تظل مرتبة.",
    },
    "zh": {
        "title": "性能 · 安全图像预处理",
        "hint": "在每次 AI 请求前并发准备图像，同时保持提供商顺序、分组上下文、SQLite 提交和恢复语义不变。",
        "workers": "图像预处理工作线程",
        "memory": "内存安全预算 (MiB)",
        "cache": "编码图像缓存条目",
        "note": "Auto 会根据 CPU、批次大小、图像尺寸和内存预算限制并发；AI 推理本身仍保持顺序。",
    },
}


def prepare_performance_environment_fields(environment_module: Any) -> None:
    current = tuple(environment_module._ENV_FIELDS)
    environment_module._ENV_FIELDS = current + tuple(
        name for name in _ENV_FIELDS if name not in current
    )
    if getattr(environment_module, "_PERFORMANCE_VALIDATION_INSTALLED", False):
        return

    base_validate = environment_module._validate_setting

    def validate_setting(name: str, value: str) -> str:
        value = base_validate(name, value)
        if name == "PRODUCT_SORTER_PREPROCESS_WORKERS" and value:
            lowered = value.strip().lower()
            if lowered in {"auto", "off", "false", "disabled", "0"}:
                return "off" if lowered != "auto" else "auto"
            try:
                number = int(lowered)
            except ValueError as exc:
                raise ValueError(
                    "PRODUCT_SORTER_PREPROCESS_WORKERS must be auto, off, or 1..16"
                ) from exc
            if not 1 <= number <= MAX_WORKERS:
                raise ValueError(
                    "PRODUCT_SORTER_PREPROCESS_WORKERS must be between 1 and 16"
                )
            return str(number)
        if name == "PRODUCT_SORTER_PREPROCESS_MEMORY_MB" and value:
            number = int(value)
            if not 128 <= number <= 8192:
                raise ValueError(
                    "PRODUCT_SORTER_PREPROCESS_MEMORY_MB must be between 128 and 8192"
                )
            return str(number)
        return value

    environment_module._validate_setting = validate_setting
    environment_module._PERFORMANCE_VALIDATION_INSTALLED = True


def apply_performance_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_collect = module.App.collect
    base_command = module.App.command
    base_start = module.App.start
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        setup_page = self.main_tabs.nametowidget(self.main_tabs.tabs()[0])
        self.vars["PRODUCT_SORTER_PREPROCESS_WORKERS"] = module.tk.StringVar(
            value=DEFAULT_WORKERS
        )
        self.vars["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"] = module.tk.StringVar(
            value=str(DEFAULT_MEMORY_MB)
        )
        if "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES" not in self.vars:
            self.vars["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"] = module.tk.StringVar(
                value=str(DEFAULT_CACHE_ENTRIES)
            )

        card = module.ttk.Frame(setup_page, style="Card.TFrame", padding=14)
        self.performance_card = card
        self.performance_title = module.ttk.Label(card, style="Section.TLabel")
        self.performance_title.pack(anchor="w")
        self.performance_hint = module.ttk.Label(
            card, style="MetricName.TLabel", wraplength=920
        )
        self.performance_hint.pack(anchor="w", pady=(4, 9))

        grid = module.ttk.Frame(card, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        self.performance_workers_label = module.ttk.Label(
            grid, style="MetricName.TLabel"
        )
        self.performance_workers_label.grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.performance_workers_box = module.ttk.Combobox(
            grid,
            textvariable=self.vars["PRODUCT_SORTER_PREPROCESS_WORKERS"],
            values=_WORKER_VALUES,
            state="readonly",
            width=12,
        )
        self.performance_workers_box.grid(row=0, column=1, sticky="w", pady=4)

        self.performance_memory_label = module.ttk.Label(
            grid, style="MetricName.TLabel"
        )
        self.performance_memory_label.grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.performance_memory_box = module.ttk.Combobox(
            grid,
            textvariable=self.vars["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"],
            values=_MEMORY_VALUES,
            width=12,
        )
        self.performance_memory_box.grid(row=1, column=1, sticky="w", pady=4)

        self.performance_cache_label = module.ttk.Label(
            grid, style="MetricName.TLabel"
        )
        self.performance_cache_label.grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.performance_cache_entry = module.ttk.Entry(
            grid,
            textvariable=self.vars["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"],
            width=12,
        )
        self.performance_cache_entry.grid(row=2, column=1, sticky="w", pady=4)

        self.performance_note = module.ttk.Label(
            card, style="MetricName.TLabel", wraplength=920
        )
        self.performance_note.pack(anchor="w", pady=(9, 0))

        actions = self.buttons["start"].master
        card.pack(fill="x", pady=(8, 8), before=actions)

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "performance_card"):
            return
        t = text(self)
        self.performance_title.config(text=t["title"])
        self.performance_hint.config(text=t["hint"])
        self.performance_workers_label.config(text=t["workers"])
        self.performance_memory_label.config(text=t["memory"])
        self.performance_cache_label.config(text=t["cache"])
        self.performance_note.config(text=t["note"])

    def load_values(self):
        base_load_values(self)
        if "PRODUCT_SORTER_PREPROCESS_WORKERS" not in self.vars:
            return
        self.vars["PRODUCT_SORTER_PREPROCESS_WORKERS"].set(
            self.values.get("PRODUCT_SORTER_PREPROCESS_WORKERS", "")
            or DEFAULT_WORKERS
        )
        self.vars["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"].set(
            self.values.get("PRODUCT_SORTER_PREPROCESS_MEMORY_MB", "")
            or str(DEFAULT_MEMORY_MB)
        )
        self.vars["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"].set(
            self.values.get("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES", "")
            or str(DEFAULT_CACHE_ENTRIES)
        )

    def collect(self):
        values = base_collect(self)
        for name in (
            "PRODUCT_SORTER_PREPROCESS_WORKERS",
            "PRODUCT_SORTER_PREPROCESS_MEMORY_MB",
            "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES",
        ):
            if name in self.vars:
                values[name] = self.vars[name].get().strip()
        return values

    def command(self):
        cmd = list(base_command(self))
        cmd += [
            "--preprocess-workers",
            self.vars["PRODUCT_SORTER_PREPROCESS_WORKERS"].get().strip(),
            "--preprocess-memory-mb",
            self.vars["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"].get().strip(),
            "--image-cache-entries",
            self.vars["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"].get().strip(),
        ]
        return cmd

    def start(self):
        workers = self.vars["PRODUCT_SORTER_PREPROCESS_WORKERS"].get().strip().lower()
        if workers not in {"auto", "off"}:
            try:
                worker_count = int(workers)
            except ValueError:
                worker_count = -1
            if not 1 <= worker_count <= MAX_WORKERS:
                module.messagebox.showerror(
                    "Performance",
                    "Preprocess workers must be auto, off, or an integer from 1 to 16.",
                )
                return None
        try:
            memory_mb = int(
                self.vars["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"].get().strip()
            )
            cache_entries = int(
                self.vars["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"].get().strip()
            )
        except ValueError:
            module.messagebox.showerror(
                "Performance", "Memory budget and image-cache entries must be integers."
            )
            return None
        if not 128 <= memory_mb <= 8192:
            module.messagebox.showerror(
                "Performance", "Memory safety budget must be between 128 and 8192 MiB."
            )
            return None
        if not 0 <= cache_entries <= 512:
            module.messagebox.showerror(
                "Performance", "Image-cache entries must be between 0 and 512."
            )
            return None
        return base_start(self)

    def set_running(self, running):
        base_set_running(self, running)
        if not hasattr(self, "performance_workers_box"):
            return
        state = "disabled" if running else "normal"
        self.performance_workers_box.config(
            state="disabled" if running else "readonly"
        )
        self.performance_memory_box.config(state=state)
        self.performance_cache_entry.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.collect = collect
    module.App.command = command
    module.App.start = start
    module.App.set_running = set_running
