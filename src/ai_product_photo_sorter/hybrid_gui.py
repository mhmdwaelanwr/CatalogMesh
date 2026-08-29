"""Desktop controls for measured hybrid visual-embedding shadow analysis."""

from __future__ import annotations

from typing import Any

from .hybrid_embeddings import (
    DEFAULT_DIFFERENT_THRESHOLD,
    DEFAULT_MODEL,
    DEFAULT_SAME_THRESHOLD,
    fastembed_available,
    install_hint,
)

_ENV_FIELDS = (
    "HYBRID_EMBEDDINGS",
    "HYBRID_EMBEDDING_MODEL",
    "HYBRID_SIMILARITY_SAME",
    "HYBRID_SIMILARITY_DIFFERENT",
    "HYBRID_EMBEDDING_BATCH_SIZE",
    "HYBRID_EMBEDDING_PARALLEL",
    "HYBRID_EMBEDDING_CACHE_DIR",
)

_MODELS = (
    "Qdrant/clip-ViT-B-32-vision",
    "Qdrant/resnet50-onnx",
    "Qdrant/Unicom-ViT-B-32",
    "Qdrant/Unicom-ViT-B-16",
)

_TEXT = {
    "en": {
        "title": "Hybrid visual embeddings · Shadow Lab",
        "hint": "Measure local image similarity before AI classification. This evaluation mode never changes product grouping yet; it creates evidence for safe future routing thresholds.",
        "enable": "Run local embedding shadow analysis",
        "model": "Embedding model",
        "same": "High-confidence same-product threshold",
        "different": "High-confidence different-product threshold",
        "ready": "Optional FastEmbed runtime detected · first model use may download weights",
        "missing": "Optional FastEmbed runtime is not installed",
        "shadow": "Measurement only · production routing stays disabled",
    },
    "ar": {
        "title": "التضمينات البصرية الهجينة · Shadow Lab",
        "hint": "قِس تشابه الصور محليًا قبل تصنيف الـAI. وضع التقييم لا يغيّر تجميع المنتجات حاليًا؛ بل يجمع أدلة لاختيار thresholds آمنة للـrouting لاحقًا.",
        "enable": "تشغيل تحليل visual embeddings المحلي في وضع Shadow",
        "model": "موديل الـembedding",
        "same": "Threshold قوي لنفس المنتج",
        "different": "Threshold قوي لمنتج مختلف",
        "ready": "FastEmbed الاختياري متاح · أول استخدام للموديل قد يحتاج تنزيل الأوزان",
        "missing": "FastEmbed الاختياري غير مثبت",
        "shadow": "قياس فقط · الـproduction routing ما زال معطلًا",
    },
    "zh": {
        "title": "混合视觉嵌入 · Shadow Lab",
        "hint": "在 AI 分类前本地测量图像相似度。评估模式暂时不会改变产品分组，只收集证据以安全校准后续路由阈值。",
        "enable": "运行本地图像嵌入 Shadow 分析",
        "model": "嵌入模型",
        "same": "高置信同一产品阈值",
        "different": "高置信不同产品阈值",
        "ready": "检测到可选 FastEmbed 运行时 · 首次使用模型可能需要下载权重",
        "missing": "未安装可选 FastEmbed 运行时",
        "shadow": "仅测量 · 生产路由仍处于禁用状态",
    },
}


def prepare_hybrid_environment_fields(environment_module: Any) -> None:
    current = tuple(environment_module._ENV_FIELDS)
    environment_module._ENV_FIELDS = current + tuple(
        name for name in _ENV_FIELDS if name not in current
    )
    if getattr(environment_module, "_HYBRID_VALIDATION_INSTALLED", False):
        return
    base_validate = environment_module._validate_setting

    def validate_setting(name: str, value: str) -> str:
        value = base_validate(name, value)
        if name == "HYBRID_EMBEDDINGS" and value:
            lowered = value.lower()
            if lowered not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                raise ValueError("HYBRID_EMBEDDINGS must be true or false")
            return "true" if lowered in {"true", "1", "yes", "on"} else "false"
        if name in {"HYBRID_SIMILARITY_SAME", "HYBRID_SIMILARITY_DIFFERENT"} and value:
            number = float(value)
            if not 0 <= number <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
            return str(number)
        if name == "HYBRID_EMBEDDING_BATCH_SIZE" and value:
            number = int(value)
            if not 1 <= number <= 256:
                raise ValueError("HYBRID_EMBEDDING_BATCH_SIZE must be between 1 and 256")
            return str(number)
        if name == "HYBRID_EMBEDDING_PARALLEL" and value:
            number = int(value)
            if not 0 <= number <= 64:
                raise ValueError("HYBRID_EMBEDDING_PARALLEL must be between 0 and 64")
            return str(number)
        return value

    environment_module._validate_setting = validate_setting
    environment_module._HYBRID_VALIDATION_INSTALLED = True


def apply_hybrid_gui(module: Any) -> None:
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
        self.vars["hybrid_embeddings"] = module.tk.BooleanVar(value=False)
        self.vars["HYBRID_EMBEDDING_MODEL"] = module.tk.StringVar(value=DEFAULT_MODEL)
        self.vars["HYBRID_SIMILARITY_SAME"] = module.tk.StringVar(value=str(DEFAULT_SAME_THRESHOLD))
        self.vars["HYBRID_SIMILARITY_DIFFERENT"] = module.tk.StringVar(value=str(DEFAULT_DIFFERENT_THRESHOLD))

        card = module.ttk.Frame(setup_page, style="Card.TFrame", padding=14)
        self.hybrid_card = card
        self.hybrid_title = module.ttk.Label(card, style="Section.TLabel")
        self.hybrid_title.pack(anchor="w")
        self.hybrid_hint = module.ttk.Label(card, style="MetricName.TLabel", wraplength=920)
        self.hybrid_hint.pack(anchor="w", pady=(4, 9))
        self.hybrid_checkbox = module.ttk.Checkbutton(
            card,
            variable=self.vars["hybrid_embeddings"],
            style="Card.TCheckbutton",
        )
        self.hybrid_checkbox.pack(anchor="w", pady=(0, 9))

        grid = module.ttk.Frame(card, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        self.hybrid_model_label = module.ttk.Label(grid, style="MetricName.TLabel")
        self.hybrid_model_label.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.hybrid_model_box = module.ttk.Combobox(
            grid,
            textvariable=self.vars["HYBRID_EMBEDDING_MODEL"],
            values=_MODELS,
            state="readonly",
        )
        self.hybrid_model_box.grid(row=0, column=1, sticky="ew", pady=4)
        self.hybrid_same_label = module.ttk.Label(grid, style="MetricName.TLabel")
        self.hybrid_same_label.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.hybrid_same_entry = module.ttk.Entry(
            grid, textvariable=self.vars["HYBRID_SIMILARITY_SAME"], width=12
        )
        self.hybrid_same_entry.grid(row=1, column=1, sticky="w", pady=4)
        self.hybrid_different_label = module.ttk.Label(grid, style="MetricName.TLabel")
        self.hybrid_different_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.hybrid_different_entry = module.ttk.Entry(
            grid, textvariable=self.vars["HYBRID_SIMILARITY_DIFFERENT"], width=12
        )
        self.hybrid_different_entry.grid(row=2, column=1, sticky="w", pady=4)
        self.hybrid_runtime = module.ttk.Label(card, style="MetricName.TLabel", wraplength=920)
        self.hybrid_runtime.pack(anchor="w", pady=(9, 0))
        self.hybrid_mode_note = module.ttk.Label(card, style="MetricName.TLabel", wraplength=920)
        self.hybrid_mode_note.pack(anchor="w", pady=(2, 0))

        actions = self.buttons["start"].master
        card.pack(fill="x", pady=(8, 8), before=actions)

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "hybrid_card"):
            return
        t = text(self)
        self.hybrid_title.config(text=t["title"])
        self.hybrid_hint.config(text=t["hint"])
        self.hybrid_checkbox.config(text=t["enable"])
        self.hybrid_model_label.config(text=t["model"])
        self.hybrid_same_label.config(text=t["same"])
        self.hybrid_different_label.config(text=t["different"])
        self.hybrid_runtime.config(text=t["ready"] if fastembed_available() else t["missing"])
        self.hybrid_mode_note.config(text=t["shadow"])

    def load_values(self):
        base_load_values(self)
        if "hybrid_embeddings" not in self.vars:
            return
        enabled = str(self.values.get("HYBRID_EMBEDDINGS", "")).strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.vars["hybrid_embeddings"].set(enabled)
        self.vars["HYBRID_EMBEDDING_MODEL"].set(
            self.values.get("HYBRID_EMBEDDING_MODEL", "") or DEFAULT_MODEL
        )
        self.vars["HYBRID_SIMILARITY_SAME"].set(
            self.values.get("HYBRID_SIMILARITY_SAME", "") or str(DEFAULT_SAME_THRESHOLD)
        )
        self.vars["HYBRID_SIMILARITY_DIFFERENT"].set(
            self.values.get("HYBRID_SIMILARITY_DIFFERENT", "") or str(DEFAULT_DIFFERENT_THRESHOLD)
        )

    def collect(self):
        values = base_collect(self)
        if "hybrid_embeddings" in self.vars:
            values["HYBRID_EMBEDDINGS"] = (
                "true" if self.vars["hybrid_embeddings"].get() else "false"
            )
            for name in (
                "HYBRID_EMBEDDING_MODEL",
                "HYBRID_SIMILARITY_SAME",
                "HYBRID_SIMILARITY_DIFFERENT",
            ):
                values[name] = self.vars[name].get().strip()
        return values

    def command(self):
        cmd = list(base_command(self))
        if "hybrid_embeddings" in self.vars and self.vars["hybrid_embeddings"].get():
            cmd += [
                "--hybrid-embeddings",
                "--hybrid-embedding-model", self.vars["HYBRID_EMBEDDING_MODEL"].get().strip(),
                "--hybrid-same-threshold", self.vars["HYBRID_SIMILARITY_SAME"].get().strip(),
                "--hybrid-different-threshold", self.vars["HYBRID_SIMILARITY_DIFFERENT"].get().strip(),
            ]
        return cmd

    def start(self):
        if "hybrid_embeddings" in self.vars and self.vars["hybrid_embeddings"].get():
            try:
                same = float(self.vars["HYBRID_SIMILARITY_SAME"].get())
                different = float(self.vars["HYBRID_SIMILARITY_DIFFERENT"].get())
            except ValueError:
                module.messagebox.showerror("Hybrid embeddings", "Similarity thresholds must be numbers between 0 and 1.")
                return None
            if not (0 <= different < same <= 1):
                module.messagebox.showerror(
                    "Hybrid embeddings",
                    "Thresholds must satisfy 0 <= different < same <= 1.",
                )
                return None
            if not fastembed_available():
                module.messagebox.showerror(
                    "Hybrid embeddings",
                    "The optional local embedding runtime is not installed.\n\n"
                    f"For the Python/PyPI build, install it with:\n{install_hint()}\n\n"
                    "This shadow feature remains disabled in binaries that were built without the optional runtime.",
                )
                return None
        return base_start(self)

    def set_running(self, running):
        base_set_running(self, running)
        if not hasattr(self, "hybrid_checkbox"):
            return
        state = "disabled" if running else "normal"
        self.hybrid_checkbox.config(state=state)
        self.hybrid_model_box.config(state="disabled" if running else "readonly")
        self.hybrid_same_entry.config(state=state)
        self.hybrid_different_entry.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.collect = collect
    module.App.command = command
    module.App.start = start
    module.App.set_running = set_running
