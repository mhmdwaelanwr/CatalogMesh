"""Desktop controls for the local-first Ollama provider."""

from __future__ import annotations

from typing import Any

from .ollama_local import (
    DEFAULT_BASE_URL,
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    discover_ollama_models,
)

_ENV_FIELDS = (
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_TIMEOUT",
    "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES",
)

_TEXT = {
    "en": {
        "tab": "OLLAMA · LOCAL",
        "title": "Local AI with Ollama",
        "hint": "Run vision models on this computer. No API key is required, product photos can stay local, and cloud providers can remain as optional fallbacks.",
        "server": "Ollama server",
        "model": "Vision model",
        "keep_alive": "Keep model loaded",
        "timeout": "Inference timeout (seconds)",
        "refresh": "Detect vision models",
        "first": "Use Ollama first",
        "only": "Local only",
        "ready": "Local AI settings ready",
        "checking": "Checking local Ollama…",
        "connected": "Connected · {count} vision model(s)",
        "none": "Connected, but no installed vision model was found",
    },
    "ar": {
        "tab": "OLLAMA · محلي",
        "title": "ذكاء اصطناعي محلي عبر Ollama",
        "hint": "شغّل موديلات الرؤية على جهازك بدون API key. الصور يمكن أن تظل محلية، مع إبقاء مزودات السحابة كخطة احتياطية اختيارية.",
        "server": "خادم Ollama",
        "model": "موديل الرؤية",
        "keep_alive": "إبقاء الموديل محمّلًا",
        "timeout": "مهلة التحليل بالثواني",
        "refresh": "اكتشاف موديلات الرؤية",
        "first": "استخدم Ollama أولًا",
        "only": "محلي فقط",
        "ready": "إعدادات الذكاء المحلي جاهزة",
        "checking": "جاري فحص Ollama المحلي…",
        "connected": "متصل · {count} موديل رؤية",
        "none": "Ollama متصل لكن لا يوجد موديل رؤية مثبت",
    },
    "zh": {
        "tab": "OLLAMA · 本地",
        "title": "Ollama 本地 AI",
        "hint": "在本机运行视觉模型，无需 API 密钥。产品图片可保留在本地，同时可将云端提供商保留为可选后备。",
        "server": "Ollama 服务器",
        "model": "视觉模型",
        "keep_alive": "保持模型加载",
        "timeout": "推理超时（秒）",
        "refresh": "检测视觉模型",
        "first": "优先使用 Ollama",
        "only": "仅本地",
        "ready": "本地 AI 设置已就绪",
        "checking": "正在检查本地 Ollama…",
        "connected": "已连接 · {count} 个视觉模型",
        "none": "Ollama 已连接，但未找到已安装的视觉模型",
    },
}


def prepare_ollama_environment_fields(environment_module: Any) -> None:
    """Expose local-AI tuning knobs in the existing Environment Center."""
    current = tuple(environment_module._ENV_FIELDS)
    environment_module._ENV_FIELDS = current + tuple(
        name for name in _ENV_FIELDS if name not in current
    )


def apply_ollama_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_collect = module.App.collect
    base_set_running = module.App.set_running

    def text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def build(self):
        base_build(self)
        api_page = self.main_tabs.nametowidget(self.main_tabs.tabs()[1])
        notebooks = [
            child for child in api_page.winfo_children()
            if isinstance(child, module.ttk.Notebook)
        ]
        if not notebooks:
            return
        key_book = notebooks[0]
        page = module.ttk.Frame(key_book, style="Panel.TFrame", padding=18)
        key_book.add(page, text="OLLAMA · LOCAL")
        self.ollama_tab = page
        self.ollama_notebook = key_book

        self.vars["OLLAMA_BASE_URL"] = module.tk.StringVar(value=DEFAULT_BASE_URL)
        self.vars["OLLAMA_MODEL"] = module.tk.StringVar(value=DEFAULT_MODEL)
        self.vars["OLLAMA_KEEP_ALIVE"] = module.tk.StringVar(value=DEFAULT_KEEP_ALIVE)
        self.vars["OLLAMA_TIMEOUT"] = module.tk.StringVar(value=str(DEFAULT_TIMEOUT))
        self.ollama_status = module.tk.StringVar(value="")

        hero = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        hero.pack(fill="x", pady=(0, 14))
        self.ollama_title = module.ttk.Label(hero, style="Metric.TLabel")
        self.ollama_title.pack(anchor="w")
        self.ollama_hint = module.ttk.Label(
            hero, style="MetricName.TLabel", wraplength=900
        )
        self.ollama_hint.pack(anchor="w", pady=(4, 10))
        module.ttk.Label(
            hero, textvariable=self.ollama_status, style="Panel.TLabel",
            font=("Sans", 10, "bold"),
        ).pack(anchor="w")

        form = module.ttk.Frame(page, style="Panel.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self.ollama_server_label = module.ttk.Label(form, style="Panel.TLabel")
        self.ollama_server_label.grid(row=0, column=0, sticky="w", padx=4, pady=7)
        self.ollama_server_entry = module.ttk.Entry(
            form, textvariable=self.vars["OLLAMA_BASE_URL"]
        )
        self.ollama_server_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=5)

        self.ollama_model_label = module.ttk.Label(form, style="Panel.TLabel")
        self.ollama_model_label.grid(row=1, column=0, sticky="w", padx=4, pady=7)
        self.ollama_model_box = module.ttk.Combobox(
            form, textvariable=self.vars["OLLAMA_MODEL"], values=[]
        )
        self.ollama_model_box.grid(row=1, column=1, sticky="ew", padx=8, pady=5)
        self.ollama_refresh_button = module.ttk.Button(
            form, style="Soft.TButton", command=self.refresh_ollama_models
        )
        self.ollama_refresh_button.grid(row=1, column=2, padx=4, pady=5)

        self.ollama_keep_alive_label = module.ttk.Label(form, style="Panel.TLabel")
        self.ollama_keep_alive_label.grid(row=2, column=0, sticky="w", padx=4, pady=7)
        self.ollama_keep_alive_entry = module.ttk.Entry(
            form, textvariable=self.vars["OLLAMA_KEEP_ALIVE"]
        )
        self.ollama_keep_alive_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=8, pady=5)

        self.ollama_timeout_label = module.ttk.Label(form, style="Panel.TLabel")
        self.ollama_timeout_label.grid(row=3, column=0, sticky="w", padx=4, pady=7)
        self.ollama_timeout_entry = module.ttk.Entry(
            form, textvariable=self.vars["OLLAMA_TIMEOUT"]
        )
        self.ollama_timeout_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=8, pady=5)

        actions = module.ttk.Frame(page, style="Card.TFrame", padding=14)
        actions.pack(fill="x", pady=(16, 0))
        self.ollama_first_button = module.ttk.Button(
            actions, style="Accent.TButton", command=self.use_ollama_first
        )
        self.ollama_first_button.pack(side="left", padx=(0, 8))
        self.ollama_only_button = module.ttk.Button(
            actions, style="Soft.TButton", command=self.use_ollama_only
        )
        self.ollama_only_button.pack(side="left")

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "ollama_tab"):
            return
        t = text(self)
        try:
            self.ollama_notebook.tab(self.ollama_tab, text=t["tab"])
        except module.tk.TclError:
            pass
        self.ollama_title.config(text=t["title"])
        self.ollama_hint.config(text=t["hint"])
        self.ollama_server_label.config(text=t["server"])
        self.ollama_model_label.config(text=t["model"])
        self.ollama_keep_alive_label.config(text=t["keep_alive"])
        self.ollama_timeout_label.config(text=t["timeout"])
        self.ollama_refresh_button.config(text=t["refresh"])
        self.ollama_first_button.config(text=t["first"])
        self.ollama_only_button.config(text=t["only"])
        if not self.ollama_status.get():
            self.ollama_status.set(t["ready"])

    def load_values(self):
        base_load_values(self)
        if "OLLAMA_BASE_URL" not in self.vars:
            return
        defaults = {
            "OLLAMA_BASE_URL": DEFAULT_BASE_URL,
            "OLLAMA_MODEL": DEFAULT_MODEL,
            "OLLAMA_KEEP_ALIVE": DEFAULT_KEEP_ALIVE,
            "OLLAMA_TIMEOUT": str(DEFAULT_TIMEOUT),
        }
        for name, default in defaults.items():
            self.vars[name].set(str(self.values.get(name, "") or default))

    def collect(self):
        values = base_collect(self)
        for name in ("OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_KEEP_ALIVE", "OLLAMA_TIMEOUT"):
            if name in self.vars:
                values[name] = self.vars[name].get().strip()
        return values

    def refresh_ollama_models(self):
        t = text(self)
        self.ollama_status.set(t["checking"])
        self.root.update_idletasks()
        try:
            models = discover_ollama_models(self.vars["OLLAMA_BASE_URL"].get(), vision_only=True)
        except Exception as exc:
            self.ollama_status.set(str(exc))
            module.messagebox.showerror("Ollama", str(exc))
            return
        self.ollama_model_box["values"] = models
        current = self.vars["OLLAMA_MODEL"].get().strip()
        if models and current not in models:
            self.vars["OLLAMA_MODEL"].set(models[0])
        self.ollama_status.set(
            t["connected"].format(count=len(models)) if models else t["none"]
        )

    def use_ollama_first(self):
        raw = self.vars.get("providers").get() if "providers" in self.vars else ""
        providers = [item.strip().lower() for item in raw.split(",") if item.strip()]
        providers = [item for item in providers if item != "ollama"]
        if not providers:
            providers = ["gemini", "openai", "anthropic"]
        self.vars["providers"].set(",".join(["ollama", *providers]))
        self.ollama_status.set("Ollama is now first in provider priority")

    def use_ollama_only(self):
        self.vars["providers"].set("ollama")
        self.ollama_status.set("Local-only mode enabled")

    def set_running(self, running):
        base_set_running(self, running)
        if not hasattr(self, "ollama_refresh_button"):
            return
        state = "disabled" if running else "normal"
        for widget in (
            self.ollama_server_entry,
            self.ollama_model_box,
            self.ollama_keep_alive_entry,
            self.ollama_timeout_entry,
            self.ollama_refresh_button,
            self.ollama_first_button,
            self.ollama_only_button,
        ):
            widget.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.collect = collect
    module.App.refresh_ollama_models = refresh_ollama_models
    module.App.use_ollama_first = use_ollama_first
    module.App.use_ollama_only = use_ollama_only
    module.App.set_running = set_running
