"""Professional in-app environment/configuration management for the desktop GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .provider_selection import ProviderSelectionError, canonical_provider_string
from .secrets_store import SECRET_NAMES, clear as clear_keyring, read as read_keyring

_ENV_FIELDS = (
    *SECRET_NAMES,
    "APP_LANGUAGE",
    "APP_THEME",
    "AI_PROVIDERS",
    "GEMINI_MODEL",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
    "ANTHROPIC_MODEL",
    "VALIDATE_KEYS",
    "USE_KEYRING",
    "COST_PER_REQUEST",
    "GEMINI_INPUT_COST_PER_MILLION",
    "GEMINI_OUTPUT_COST_PER_MILLION",
    "OPENAI_INPUT_COST_PER_MILLION",
    "OPENAI_OUTPUT_COST_PER_MILLION",
    "ANTHROPIC_INPUT_COST_PER_MILLION",
    "ANTHROPIC_OUTPUT_COST_PER_MILLION",
    "PRODUCT_SOURCE",
    "PRODUCT_OUTPUT",
    "PRICES_FILE",
    "BATCH_SIZE",
    "CONFIDENCE",
    "MAX_RETRIES",
    "PHOTO_LIMIT",
    "PRODUCT_SORTER_MD_REPORT",
    "BENCHMARK_LIMIT",
    "PRODUCT_SORTER_OUTPUT_MODE",
)

_SENSITIVE = set(SECRET_NAMES)
_BOOL_FIELDS = {"VALIDATE_KEYS", "USE_KEYRING", "PRODUCT_SORTER_MD_REPORT"}
_COST_FIELDS = {
    "COST_PER_REQUEST",
    "GEMINI_INPUT_COST_PER_MILLION",
    "GEMINI_OUTPUT_COST_PER_MILLION",
    "OPENAI_INPUT_COST_PER_MILLION",
    "OPENAI_OUTPUT_COST_PER_MILLION",
    "ANTHROPIC_INPUT_COST_PER_MILLION",
    "ANTHROPIC_OUTPUT_COST_PER_MILLION",
}

_TEXT = {
    "en": {
        "tab": "Environment",
        "title": "Environment Center",
        "hint": "Edit Product Sorter configuration without leaving the desktop app. API keys stay masked and the .env file remains private.",
        "file": "Configuration file",
        "reload": "Reload",
        "save_all": "Save all",
        "clear_keys": "Clear API keys",
        "delete": "Delete configuration",
        "settings": "SETTINGS",
        "name": "Setting",
        "value": "Value",
        "editor": "SETTING EDITOR",
        "set": "Set value",
        "clear": "Clear value",
        "saved": "Configuration saved",
        "reloaded": "Configuration reloaded",
        "cleared": "Value cleared",
        "keys_cleared": "API keys cleared from .env and OS keyring",
        "deleted": "Configuration removed; defaults are now shown",
        "select": "Select a setting to edit.",
    },
    "ar": {
        "tab": "Environment",
        "title": "مركز الإعدادات",
        "hint": "عدّل إعدادات Product Sorter من داخل البرنامج. مفاتيح API تظل مخفية وملف .env يظل خاصًا.",
        "file": "ملف الإعدادات",
        "reload": "إعادة تحميل",
        "save_all": "حفظ الكل",
        "clear_keys": "مسح مفاتيح API",
        "delete": "حذف الإعدادات",
        "settings": "الإعدادات",
        "name": "الإعداد",
        "value": "القيمة",
        "editor": "تعديل الإعداد",
        "set": "حفظ القيمة",
        "clear": "مسح القيمة",
        "saved": "تم حفظ الإعدادات",
        "reloaded": "تمت إعادة تحميل الإعدادات",
        "cleared": "تم مسح القيمة",
        "keys_cleared": "تم مسح مفاتيح API من .env و OS keyring",
        "deleted": "تم حذف الإعدادات وعرض القيم الافتراضية",
        "select": "اختر إعدادًا لتعديله.",
    },
    "zh": {
        "tab": "Environment",
        "title": "环境配置中心",
        "hint": "无需离开桌面应用即可编辑 Product Sorter 配置。API 密钥保持隐藏，.env 文件保持私密。",
        "file": "配置文件",
        "reload": "重新加载",
        "save_all": "全部保存",
        "clear_keys": "清除 API 密钥",
        "delete": "删除配置",
        "settings": "设置",
        "name": "设置项",
        "value": "值",
        "editor": "设置编辑器",
        "set": "设置值",
        "clear": "清除值",
        "saved": "配置已保存",
        "reloaded": "配置已重新加载",
        "cleared": "值已清除",
        "keys_cleared": "API 密钥已从 .env 和系统密钥环清除",
        "deleted": "配置已删除，当前显示默认值",
        "select": "请选择要编辑的设置。",
    },
}


def _mask_value(name: str, value: str) -> str:
    if not value:
        return ""
    if name in _SENSITIVE:
        return "••••••••"
    return value


def _bool_value(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return "true"
    if lowered in {"0", "false", "no", "off"}:
        return "false"
    raise ValueError("value must be true or false")


def _validate_setting(name: str, value: str) -> str:
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise ValueError("value cannot contain a newline")
    if name == "AI_PROVIDERS":
        try:
            canonical, _ = canonical_provider_string(value)
        except ProviderSelectionError as exc:
            raise ValueError(str(exc)) from exc
        return canonical
    if name in _BOOL_FIELDS and value:
        return _bool_value(value)
    if name == "BATCH_SIZE" and value:
        number = int(value)
        if not 3 <= number <= 8:
            raise ValueError("BATCH_SIZE must be between 3 and 8")
        return str(number)
    if name == "CONFIDENCE" and value:
        number = float(value)
        if not 0 <= number <= 1:
            raise ValueError("CONFIDENCE must be between 0 and 1")
        return str(number)
    if name == "MAX_RETRIES" and value:
        number = int(value)
        if not 0 <= number <= 20:
            raise ValueError("MAX_RETRIES must be between 0 and 20")
        return str(number)
    if name in {"PHOTO_LIMIT", "BENCHMARK_LIMIT"} and value:
        number = int(value)
        if number <= 0:
            raise ValueError(f"{name} must be a positive integer or blank")
        return str(number)
    if name in _COST_FIELDS and value:
        number = float(value)
        if number < 0:
            raise ValueError(f"{name} cannot be negative")
        return value
    if name == "APP_THEME" and value and value not in {"dark", "light"}:
        raise ValueError("APP_THEME must be dark or light")
    if name == "APP_LANGUAGE" and value and value not in {"ar", "en", "zh"}:
        raise ValueError("APP_LANGUAGE must be ar, en or zh")
    if name == "PRODUCT_SORTER_OUTPUT_MODE" and value:
        mode = value.lower()
        if mode not in {"copy", "auto", "hardlink", "symlink"}:
            raise ValueError("output mode must be copy, auto, hardlink or symlink")
        return mode
    return value


def apply_environment_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_load_values = module.App.load_values
    base_set_running = module.App.set_running

    def _text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def _merge_keyring_values(self):
        use_keyring = str(self.values.get("USE_KEYRING", "")).strip().lower() in {
            "1", "true", "yes", "on"
        }
        if use_keyring:
            for name, value in read_keyring().items():
                if value and not self.values.get(name):
                    self.values[name] = value

    def build(self):
        base_build(self)
        self.env_selected_name = module.tk.StringVar(value="")
        self.env_edit_value = module.tk.StringVar(value="")
        self.env_status = module.tk.StringVar(value="")

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=20)
        self.main_tabs.insert(4, page, text="Environment")
        self.environment_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        header.pack(fill="x", pady=(0, 12))
        self.env_title = module.ttk.Label(header, style="Metric.TLabel")
        self.env_title.pack(anchor="w")
        self.env_hint = module.ttk.Label(header, style="MetricName.TLabel", wraplength=950)
        self.env_hint.pack(anchor="w", pady=(4, 12))

        path_row = module.ttk.Frame(header, style="Card.TFrame")
        path_row.pack(fill="x")
        self.env_file_label = module.ttk.Label(path_row, style="MetricName.TLabel")
        self.env_file_label.pack(side="left")
        module.ttk.Label(
            path_row,
            text=str(module.ENV_FILE),
            style="Panel.TLabel",
            font=("Monospace", 9),
        ).pack(side="left", padx=(8, 0))

        actions = module.ttk.Frame(header, style="Card.TFrame")
        actions.pack(fill="x", pady=(14, 0))
        self.env_reload_button = module.ttk.Button(actions, style="Soft.TButton", command=self.reload_environment)
        self.env_reload_button.pack(side="left", padx=(0, 7))
        self.env_save_button = module.ttk.Button(actions, style="Accent.TButton", command=self.save_environment)
        self.env_save_button.pack(side="left", padx=(0, 7))
        self.env_clear_keys_button = module.ttk.Button(actions, style="Soft.TButton", command=self.clear_environment_keys)
        self.env_clear_keys_button.pack(side="left", padx=(0, 7))
        self.env_delete_button = module.ttk.Button(actions, style="Danger.TButton", command=self.delete_environment)
        self.env_delete_button.pack(side="left")
        module.ttk.Label(actions, textvariable=self.env_status, style="MetricName.TLabel").pack(side="right")

        paned = module.ttk.Panedwindow(page, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = module.ttk.Frame(paned, style="Card.TFrame", padding=12)
        right = module.ttk.Frame(paned, style="Card.TFrame", padding=18)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        self.env_settings_label = module.ttk.Label(left, style="Section.TLabel")
        self.env_settings_label.pack(anchor="w", pady=(0, 8))
        self.env_tree = module.ttk.Treeview(left, columns=("name", "value"), show="headings", selectmode="browse")
        self.env_tree.column("name", width=330, anchor="w")
        self.env_tree.column("value", width=330, anchor="w")
        self.env_tree.pack(fill="both", expand=True)
        self.env_tree.bind("<<TreeviewSelect>>", self.select_environment_setting)

        self.env_editor_label = module.ttk.Label(right, style="Section.TLabel")
        self.env_editor_label.pack(anchor="w", pady=(0, 14))
        self.env_name_label = module.ttk.Label(right, style="MetricName.TLabel")
        self.env_name_label.pack(anchor="w")
        self.env_name_box = module.ttk.Combobox(
            right,
            textvariable=self.env_selected_name,
            values=list(_ENV_FIELDS),
            state="readonly",
        )
        self.env_name_box.pack(fill="x", pady=(5, 14))
        self.env_name_box.bind("<<ComboboxSelected>>", self.select_environment_name)
        self.env_value_label = module.ttk.Label(right, style="MetricName.TLabel")
        self.env_value_label.pack(anchor="w")
        self.env_value_entry = module.ttk.Entry(right, textvariable=self.env_edit_value)
        self.env_value_entry.pack(fill="x", pady=(5, 14))
        editor_actions = module.ttk.Frame(right, style="Card.TFrame")
        editor_actions.pack(fill="x")
        self.env_set_button = module.ttk.Button(editor_actions, style="Accent.TButton", command=self.set_environment_value)
        self.env_set_button.pack(side="left", padx=(0, 7))
        self.env_clear_button = module.ttk.Button(editor_actions, style="Soft.TButton", command=self.clear_environment_value)
        self.env_clear_button.pack(side="left")
        self.env_editor_hint = module.ttk.Label(right, style="MetricName.TLabel", wraplength=430)
        self.env_editor_hint.pack(anchor="w", pady=(18, 0))

        self.refresh_environment_tree()

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "environment_page"):
            return
        text = _text(self)
        self.main_tabs.tab(4, text=text["tab"])
        if len(self.main_tabs.tabs()) > 5:
            self.main_tabs.tab(5, text=self.t("about"))
        self.env_title.config(text=text["title"])
        self.env_hint.config(text=text["hint"])
        self.env_file_label.config(text=text["file"] + ":")
        self.env_reload_button.config(text=text["reload"])
        self.env_save_button.config(text=text["save_all"])
        self.env_clear_keys_button.config(text=text["clear_keys"])
        self.env_delete_button.config(text=text["delete"])
        self.env_settings_label.config(text=text["settings"])
        self.env_editor_label.config(text=text["editor"])
        self.env_name_label.config(text=text["name"])
        self.env_value_label.config(text=text["value"])
        self.env_set_button.config(text=text["set"])
        self.env_clear_button.config(text=text["clear"])
        self.env_tree.heading("name", text=text["name"])
        self.env_tree.heading("value", text=text["value"])
        if not self.env_editor_hint.cget("text"):
            self.env_editor_hint.config(text=text["select"])

    def load_values(self):
        _merge_keyring_values(self)
        base_load_values(self)
        if hasattr(self, "env_tree"):
            self.refresh_environment_tree()

    def refresh_environment_tree(self):
        if not hasattr(self, "env_tree"):
            return
        selected = self.env_selected_name.get()
        self.env_tree.delete(*self.env_tree.get_children())
        for name in _ENV_FIELDS:
            value = str(self.values.get(name, ""))
            self.env_tree.insert("", "end", iid=name, values=(name, _mask_value(name, value)))
        if selected in _ENV_FIELDS and self.env_tree.exists(selected):
            self.env_tree.selection_set(selected)
            self.env_tree.see(selected)

    def _load_editor(self, name: str):
        if name not in _ENV_FIELDS:
            return
        self.env_selected_name.set(name)
        self.env_edit_value.set(str(self.values.get(name, "")))
        self.env_value_entry.config(show="•" if name in _SENSITIVE else "")
        self.env_editor_hint.config(
            text=("Sensitive value — hidden in the settings table and activity log."
                  if name in _SENSITIVE else f"Editing {name}")
        )

    def select_environment_setting(self, event=None):
        selected = self.env_tree.selection()
        if selected:
            self._load_editor(selected[0])

    def select_environment_name(self, event=None):
        self._load_editor(self.env_selected_name.get())

    def _persist_environment(self, status_text: str):
        module.save_env(self.values)
        base_load_values(self)
        self.refresh_environment_tree()
        self.env_status.set(status_text)

    def set_environment_value(self):
        name = self.env_selected_name.get().strip()
        if name not in _ENV_FIELDS:
            module.messagebox.showerror("Environment", _text(self)["select"])
            return
        try:
            value = _validate_setting(name, self.env_edit_value.get())
        except (ValueError, TypeError) as exc:
            module.messagebox.showerror("Environment", str(exc))
            return
        self.values[name] = value
        self.env_edit_value.set(value)
        self._persist_environment(_text(self)["saved"])

    def clear_environment_value(self):
        name = self.env_selected_name.get().strip()
        if name not in _ENV_FIELDS:
            module.messagebox.showerror("Environment", _text(self)["select"])
            return
        self.values[name] = ""
        if name in _SENSITIVE:
            clear_keyring((name,))
        self.env_edit_value.set("")
        self._persist_environment(_text(self)["cleared"])

    def save_environment(self):
        self.values = self.collect()
        module.save_env(self.values)
        self.refresh_environment_tree()
        self.env_status.set(_text(self)["saved"])

    def reload_environment(self):
        self.values = module.read_env(module.ENV_FILE)
        _merge_keyring_values(self)
        base_load_values(self)
        self.refresh_environment_tree()
        if self.env_selected_name.get() in _ENV_FIELDS:
            self._load_editor(self.env_selected_name.get())
        self.env_status.set(_text(self)["reloaded"])

    def clear_environment_keys(self):
        if not module.messagebox.askyesno(
            "Environment",
            "Clear all configured API keys from the .env file and the OS keyring?",
        ):
            return
        for name in SECRET_NAMES:
            self.values[name] = ""
            if name in self.vars:
                self.vars[name].set("")
        clear_keyring()
        self._persist_environment(_text(self)["keys_cleared"])
        if self.env_selected_name.get() in _SENSITIVE:
            self.env_edit_value.set("")

    def delete_environment(self):
        if not module.messagebox.askyesno(
            "Environment",
            "Delete the Product Sorter .env configuration and clear stored API keys from the OS keyring?",
        ):
            return
        try:
            Path(module.ENV_FILE).unlink(missing_ok=True)
        except OSError as exc:
            module.messagebox.showerror("Environment", f"Could not delete configuration: {exc}")
            return
        clear_keyring()
        self.values = {}
        base_load_values(self)
        self.env_selected_name.set("")
        self.env_edit_value.set("")
        self.refresh_environment_tree()
        self.env_status.set(_text(self)["deleted"])

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "env_save_button"):
            state = "disabled" if running else "normal"
            for button in (
                self.env_reload_button,
                self.env_save_button,
                self.env_clear_keys_button,
                self.env_delete_button,
                self.env_set_button,
                self.env_clear_button,
            ):
                button.config(state=state)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.load_values = load_values
    module.App.refresh_environment_tree = refresh_environment_tree
    module.App.select_environment_setting = select_environment_setting
    module.App.select_environment_name = select_environment_name
    module.App._load_editor = _load_editor
    module.App._persist_environment = _persist_environment
    module.App.set_environment_value = set_environment_value
    module.App.clear_environment_value = clear_environment_value
    module.App.save_environment = save_environment
    module.App.reload_environment = reload_environment
    module.App.clear_environment_keys = clear_environment_keys
    module.App.delete_environment = delete_environment
    module.App.set_running = set_running
