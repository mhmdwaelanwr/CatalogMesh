"""Global desktop i18n runtime for GUI text that escapes feature catalogs.

Most feature workspaces already provide parallel English/Arabic/Chinese
catalogs.  This module builds one reverse translation index from all loaded GUI
catalogs and uses it as a final presentation pass for widgets, notebook tabs,
tree headings, status StringVars and dialogs.  Unknown technical values (paths,
model IDs, exception details, etc.) are deliberately left untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import string
import sys
from typing import Any, Iterable

from .arabic_ui import shape_arabic_for_tk
from . import i18n as core_i18n

SUPPORTED_LANGUAGES = ("en", "ar", "zh")

# Small compatibility catalog for legacy literals which pre-date the per-feature
# _TEXT dictionaries.  Feature catalogs remain the primary source of truth.
_FALLBACK = {
    "en": {
        "Browse…": "Browse…",
        "Workspace": "Workspace",
        "API key": "API key",
        "Models": "Models",
        "Provider configuration": "Provider configuration",
        "Provider configuration needs attention": "Provider configuration needs attention",
        "Local Evidence": "Local Evidence",
        "Review Center": "Review Center",
        "SKU Match": "SKU Match",
        "Exports": "Exports",
        "Calibration": "Calibration",
        "Hybrid Routing Lab": "Hybrid Routing Lab",
        "Hybrid embeddings": "Hybrid embeddings",
        "Performance": "Performance",
        "Environment": "Environment",
        "Benchmark": "Benchmark",
        "Reports": "Reports",
        "Shopify": "Shopify",
        "Ollama": "Ollama",
        "Storage": "Storage",
        "Source and output are required": "Source and output are required",
        "Enter at least one {provider} API key first.": "Enter at least one {provider} API key first.",
        "All {provider} keys are exhausted. Enter a new key to continue:": "All {provider} keys are exhausted. Enter a new key to continue:",
        "Approved groups CSV and catalog file are required.": "Approved groups CSV and catalog file are required.",
        "SKU match manifest is required.": "SKU match manifest is required.",
        "Choose the product photo source folder first.": "Choose the product photo source folder first.",
        "Similarity thresholds must be numbers between 0 and 1.": "Similarity thresholds must be numbers between 0 and 1.",
        "Benchmark photo count must be a positive integer.": "Benchmark photo count must be a positive integer.",
    },
    "ar": {
        "Browse…": "استعراض…",
        "Workspace": "مساحة العمل",
        "API key": "مفتاح API",
        "Models": "الموديلات",
        "Provider configuration": "إعداد مزودي الذكاء الاصطناعي",
        "Provider configuration needs attention": "إعداد المزودات يحتاج إلى مراجعة",
        "Local Evidence": "الأدلة المحلية",
        "Review Center": "مركز المراجعة",
        "SKU Match": "مطابقة SKU",
        "Exports": "التصدير",
        "Calibration": "المعايرة",
        "Hybrid Routing Lab": "مختبر التوجيه الهجين",
        "Hybrid embeddings": "التضمينات الهجينة",
        "Performance": "الأداء",
        "Environment": "البيئة والإعدادات",
        "Benchmark": "اختبار الأداء",
        "Reports": "التقارير",
        "Shopify": "Shopify",
        "Ollama": "Ollama",
        "Storage": "التخزين",
        "Source and output are required": "مجلد الصور ومجلد النتائج مطلوبان",
        "Enter at least one {provider} API key first.": "أدخل مفتاح API واحدًا على الأقل لـ {provider} أولًا.",
        "All {provider} keys are exhausted. Enter a new key to continue:": "انتهت كل مفاتيح {provider}. أدخل مفتاحًا جديدًا للمتابعة:",
        "Approved groups CSV and catalog file are required.": "ملف مجموعات CSV المعتمد وملف الكتالوج مطلوبان.",
        "SKU match manifest is required.": "ملف بيان مطابقة SKU مطلوب.",
        "Choose the product photo source folder first.": "اختر مجلد صور المنتجات أولًا.",
        "Similarity thresholds must be numbers between 0 and 1.": "يجب أن تكون حدود التشابه أرقامًا بين 0 و1.",
        "Benchmark photo count must be a positive integer.": "يجب أن يكون عدد صور اختبار الأداء عددًا صحيحًا موجبًا.",
    },
    "zh": {
        "Browse…": "浏览…",
        "Workspace": "工作区",
        "API key": "API 密钥",
        "Models": "模型",
        "Provider configuration": "提供商配置",
        "Provider configuration needs attention": "提供商配置需要检查",
        "Local Evidence": "本地证据",
        "Review Center": "审核中心",
        "SKU Match": "SKU 匹配",
        "Exports": "导出",
        "Calibration": "校准",
        "Hybrid Routing Lab": "混合路由实验室",
        "Hybrid embeddings": "混合嵌入",
        "Performance": "性能",
        "Environment": "环境设置",
        "Benchmark": "基准测试",
        "Reports": "报告",
        "Shopify": "Shopify",
        "Ollama": "Ollama",
        "Storage": "存储",
        "Source and output are required": "必须选择源图片文件夹和输出文件夹",
        "Enter at least one {provider} API key first.": "请先至少输入一个 {provider} API 密钥。",
        "All {provider} keys are exhausted. Enter a new key to continue:": "所有 {provider} 密钥均已耗尽。请输入新密钥以继续：",
        "Approved groups CSV and catalog file are required.": "需要已批准的分组 CSV 和目录文件。",
        "SKU match manifest is required.": "需要 SKU 匹配清单。",
        "Choose the product photo source folder first.": "请先选择产品图片源文件夹。",
        "Similarity thresholds must be numbers between 0 and 1.": "相似度阈值必须是 0 到 1 之间的数字。",
        "Benchmark photo count must be a positive integer.": "基准测试图片数量必须是正整数。",
    },
}

_FORMATTER = string.Formatter()


def _placeholder_names(value: str) -> tuple[str, ...]:
    names: list[str] = []
    try:
        for _literal, field, _spec, _conversion in _FORMATTER.parse(value):
            if field is not None:
                names.append(field)
    except ValueError:
        return ()
    return tuple(names)


def _walk_parallel(en: Any, ar: Any, zh: Any) -> Iterable[tuple[str, str, str]]:
    if isinstance(en, str) and isinstance(ar, str) and isinstance(zh, str):
        yield en, ar, zh
        return
    if isinstance(en, dict) and isinstance(ar, dict) and isinstance(zh, dict):
        for key in en:
            if key in ar and key in zh:
                yield from _walk_parallel(en[key], ar[key], zh[key])
        return
    if isinstance(en, (tuple, list)) and isinstance(ar, type(en)) and isinstance(zh, type(en)):
        for e_item, a_item, z_item in zip(en, ar, zh):
            yield from _walk_parallel(e_item, a_item, z_item)


def _language_first_triplets(catalog: Any) -> Iterable[tuple[str, str, str]]:
    if not isinstance(catalog, dict):
        return ()
    if not all(lang in catalog for lang in SUPPORTED_LANGUAGES):
        return ()
    return tuple(_walk_parallel(catalog["en"], catalog["ar"], catalog["zh"]))


def _core_triplets() -> Iterable[tuple[str, str, str]]:
    for item in getattr(core_i18n, "TEXT", {}).values():
        if isinstance(item, dict) and all(lang in item for lang in SUPPORTED_LANGUAGES):
            values = tuple(item[lang] for lang in SUPPORTED_LANGUAGES)
            if all(isinstance(value, str) for value in values):
                yield values  # type: ignore[misc]


def collect_translation_triplets(package_prefix: str = "ai_product_photo_sorter") -> tuple[tuple[str, str, str], ...]:
    """Collect parallel text entries from every already-loaded GUI catalog."""
    triplets: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(items: Iterable[tuple[str, str, str]]) -> None:
        for values in items:
            if values not in seen:
                seen.add(values)
                triplets.append(values)

    add(_language_first_triplets(_FALLBACK))
    add(_core_triplets())
    for name, loaded in tuple(sys.modules.items()):
        if loaded is None or not name.startswith(package_prefix):
            continue
        for attr in ("L", "_TEXT", "_REPORT_TEXT"):
            add(_language_first_triplets(getattr(loaded, attr, None)))
    return tuple(triplets)


def validate_loaded_catalogs(package_prefix: str = "ai_product_photo_sorter") -> tuple[str, ...]:
    """Return structural/placeholder errors for loaded three-language catalogs."""
    errors: list[str] = []
    catalogs: list[tuple[str, Any]] = [("fallback", _FALLBACK)]
    for name, loaded in tuple(sys.modules.items()):
        if loaded is None or not name.startswith(package_prefix):
            continue
        for attr in ("L", "_TEXT", "_REPORT_TEXT"):
            catalog = getattr(loaded, attr, None)
            if isinstance(catalog, dict) and any(lang in catalog for lang in SUPPORTED_LANGUAGES):
                catalogs.append((f"{name}.{attr}", catalog))

    def validate_node(label: str, path: str, en: Any, ar: Any, zh: Any) -> None:
        if isinstance(en, str):
            if not isinstance(ar, str) or not isinstance(zh, str):
                errors.append(f"{label}:{path}: translation type mismatch")
                return
            expected = set(_placeholder_names(en))
            for language, value in (("ar", ar), ("zh", zh)):
                if set(_placeholder_names(value)) != expected:
                    errors.append(f"{label}:{path}: placeholder mismatch for {language}")
            return
        if isinstance(en, dict):
            if not isinstance(ar, dict) or not isinstance(zh, dict):
                errors.append(f"{label}:{path}: translation object mismatch")
                return
            en_keys = set(en)
            for language, branch in (("ar", ar), ("zh", zh)):
                missing = sorted(en_keys - set(branch))
                extra = sorted(set(branch) - en_keys)
                if missing:
                    errors.append(f"{label}:{path}: {language} missing keys {missing}")
                if extra:
                    errors.append(f"{label}:{path}: {language} extra keys {extra}")
            for key in en_keys & set(ar) & set(zh):
                validate_node(label, f"{path}.{key}", en[key], ar[key], zh[key])
            return
        if isinstance(en, (tuple, list)):
            if not isinstance(ar, type(en)) or not isinstance(zh, type(en)):
                errors.append(f"{label}:{path}: translation sequence mismatch")
                return
            if len(en) != len(ar) or len(en) != len(zh):
                errors.append(f"{label}:{path}: translation sequence length mismatch")
                return
            for index, (e_item, a_item, z_item) in enumerate(zip(en, ar, zh)):
                validate_node(label, f"{path}[{index}]", e_item, a_item, z_item)

    for label, catalog in catalogs:
        missing_languages = [lang for lang in SUPPORTED_LANGUAGES if lang not in catalog]
        if missing_languages:
            errors.append(f"{label}: missing languages {missing_languages}")
            continue
        validate_node(label, "root", catalog["en"], catalog["ar"], catalog["zh"])
    return tuple(errors)


@dataclass(frozen=True)
class _Template:
    regex: re.Pattern[str]
    fields: tuple[str, ...]
    target: str


class TranslationIndex:
    def __init__(self, triplets: Iterable[tuple[str, str, str]]):
        self._exact: dict[str, dict[str, str]] = {lang: {} for lang in SUPPORTED_LANGUAGES}
        self._templates: dict[str, list[_Template]] = {lang: [] for lang in SUPPORTED_LANGUAGES}
        for triplet in triplets:
            values = dict(zip(SUPPORTED_LANGUAGES, triplet))
            for source_lang, source in values.items():
                if not source:
                    continue
                for target_lang in SUPPORTED_LANGUAGES:
                    self._exact[target_lang].setdefault(source, values[target_lang])
                fields = _placeholder_names(source)
                if fields:
                    pattern = self._compile_template(source, fields)
                    if pattern is not None:
                        for target_lang in SUPPORTED_LANGUAGES:
                            self._templates[target_lang].append(
                                _Template(pattern, fields, values[target_lang])
                            )

    @staticmethod
    def _compile_template(template: str, fields: tuple[str, ...]) -> re.Pattern[str] | None:
        pieces: list[str] = ["^"]
        used: set[str] = set()
        try:
            for literal, field, _spec, _conversion in _FORMATTER.parse(template):
                pieces.append(re.escape(literal))
                if field is not None:
                    # Repeated format field names are handled as ordinary captures;
                    # the last value wins when formatting the translated template.
                    safe = re.sub(r"\W+", "_", field) or "value"
                    if safe in used:
                        pieces.append("(.+?)")
                    else:
                        pieces.append(f"(?P<{safe}>.+?)")
                        used.add(safe)
            pieces.append("$")
            return re.compile("".join(pieces), re.DOTALL)
        except (ValueError, re.error):
            return None

    def translate(self, value: object, language: str) -> str:
        text = "" if value is None else str(value)
        lang = language if language in SUPPORTED_LANGUAGES else "en"
        translated = self._exact[lang].get(text)
        if translated is None:
            for item in self._templates[lang]:
                match = item.regex.fullmatch(text)
                if not match:
                    continue
                values = match.groupdict()
                try:
                    translated = item.target.format(**values)
                except (KeyError, ValueError):
                    translated = None
                if translated is not None:
                    break
        if translated is None:
            translated = text
        if lang == "ar":
            translated = shape_arabic_for_tk(translated)
        return translated


def _walk_widgets(widget: Any) -> Iterable[Any]:
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        yield from _walk_widgets(child)


def apply_global_gui_i18n(module: Any) -> None:
    """Install final translation pass after every GUI feature extension."""
    index = TranslationIndex(collect_translation_triplets())
    module.GUI_TRANSLATION_INDEX = index
    module.GUI_I18N_CATALOG_ERRORS = validate_loaded_catalogs()
    module.CURRENT_UI_LANGUAGE = "en"

    base_build = module.App.build
    base_apply_language = module.App.apply_language

    def ui_translate(self, value):
        return module.GUI_TRANSLATION_INDEX.translate(value, self.lang)

    def _translate_widgets(self):
        for widget in _walk_widgets(self.root):
            try:
                current = widget.cget("text")
            except Exception:
                current = None
            if isinstance(current, str) and current:
                translated = self.ui_translate(current)
                if translated != current:
                    try:
                        widget.configure(text=translated)
                    except Exception:
                        pass

            if isinstance(widget, module.ttk.Notebook):
                for tab_id in widget.tabs():
                    try:
                        current_tab = widget.tab(tab_id, "text")
                        translated_tab = self.ui_translate(current_tab)
                        if translated_tab != current_tab:
                            widget.tab(tab_id, text=translated_tab)
                    except module.tk.TclError:
                        pass

            if isinstance(widget, module.ttk.Treeview):
                columns = ["#0", *tuple(widget.cget("columns"))]
                for column in columns:
                    try:
                        current_heading = widget.heading(column, "text")
                        translated_heading = self.ui_translate(current_heading)
                        if translated_heading != current_heading:
                            widget.heading(column, text=translated_heading)
                    except module.tk.TclError:
                        pass

            if isinstance(widget, module.ttk.Combobox):
                try:
                    values = tuple(widget.cget("values"))
                    translated_values = tuple(self.ui_translate(value) for value in values)
                    if translated_values != values:
                        widget.configure(values=translated_values)
                except module.tk.TclError:
                    pass

            if isinstance(widget, (module.ttk.Entry, module.ttk.Combobox)):
                try:
                    widget.configure(justify="right" if self.lang == "ar" else "left")
                except module.tk.TclError:
                    pass

    def _bind_status_variables(self):
        user_values = set(id(value) for value in getattr(self, "vars", {}).values())
        bound = getattr(self, "_i18n_bound_vars", set())
        guard = getattr(self, "_i18n_var_guard", set())
        self._i18n_bound_vars = bound
        self._i18n_var_guard = guard
        for value in self.__dict__.values():
            if not isinstance(value, module.tk.StringVar):
                continue
            identity = id(value)
            if identity in user_values or identity in bound:
                continue
            bound.add(identity)

            def on_write(*_args, variable=value, var_id=identity):
                if var_id in self._i18n_var_guard:
                    return
                current = variable.get()
                translated = self.ui_translate(current)
                if translated == current:
                    return
                self._i18n_var_guard.add(var_id)
                try:
                    variable.set(translated)
                finally:
                    self._i18n_var_guard.discard(var_id)

            value.trace_add("write", on_write)

    def build(self):
        base_build(self)
        self._bind_status_variables()

    def apply_language(self):
        module.CURRENT_UI_LANGUAGE = self.lang
        base_apply_language(self)
        self._bind_status_variables()
        self._translate_widgets()
        # Translate current status values as well as future writes.
        user_values = set(id(value) for value in getattr(self, "vars", {}).values())
        for value in self.__dict__.values():
            if isinstance(value, module.tk.StringVar) and id(value) not in user_values:
                current = value.get()
                translated = self.ui_translate(current)
                if translated != current:
                    value.set(translated)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.ui_translate = ui_translate
    module.App._translate_widgets = _translate_widgets
    module.App._bind_status_variables = _bind_status_variables

    # Dialogs are not part of the Tk widget tree. Translate known titles and
    # messages at call time; unknown exception text is intentionally preserved.
    def install_dialog_wrapper(name: str) -> None:
        original = getattr(module.messagebox, name, None)
        if original is None or getattr(original, "_catalogmesh_i18n", False):
            return

        def wrapped(title, message, *args, **kwargs):
            language = getattr(module, "CURRENT_UI_LANGUAGE", "en")
            return original(
                module.GUI_TRANSLATION_INDEX.translate(title, language),
                module.GUI_TRANSLATION_INDEX.translate(message, language),
                *args,
                **kwargs,
            )

        wrapped._catalogmesh_i18n = True  # type: ignore[attr-defined]
        setattr(module.messagebox, name, wrapped)

    for dialog_name in (
        "showerror", "showwarning", "showinfo", "askyesno", "askokcancel",
        "askretrycancel", "askquestion", "askyesnocancel",
    ):
        install_dialog_wrapper(dialog_name)

    original_askstring = getattr(module.simpledialog, "askstring", None)
    if original_askstring is not None and not getattr(original_askstring, "_catalogmesh_i18n", False):
        def askstring(title, prompt, *args, **kwargs):
            language = getattr(module, "CURRENT_UI_LANGUAGE", "en")
            return original_askstring(
                module.GUI_TRANSLATION_INDEX.translate(title, language),
                module.GUI_TRANSLATION_INDEX.translate(prompt, language),
                *args,
                **kwargs,
            )

        askstring._catalogmesh_i18n = True  # type: ignore[attr-defined]
        module.simpledialog.askstring = askstring
