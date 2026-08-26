"""Interactive CLI choice for the optional smart Markdown report.

Normal CLI users should not need to discover a hidden flag. This wrapper asks
once during interactive setup, while explicit flags and non-interactive workers
remain deterministic for scripts, CI, and the desktop GUI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .smart_report import REPORT_ENV

_YES = {"y", "yes", "1", "true", "on", "نعم", "اه", "آه", "ايوه", "أيوه"}
_NO = {"n", "no", "0", "false", "off", "لا", "لأ"}


def _language() -> str:
    value = os.getenv("APP_LANGUAGE", "en").strip().lower()
    return value if value in {"ar", "en", "zh"} else "en"


def _question(default: bool) -> str:
    suffix = "[Y/n]" if default else "[y/N]"
    language = _language()
    if language == "ar":
        return f"إنشاء تقرير Markdown ذكي شامل بعد انتهاء الفرز؟ {suffix}: "
    if language == "zh":
        return f"排序完成后生成完整的智能 Markdown 报告？ {suffix}: "
    return f"Generate a comprehensive smart Markdown report after sorting? {suffix}: "


def choose_report(default: bool) -> bool:
    """Ask an interactive yes/no question, using the configured value as default."""
    while True:
        try:
            value = input(_question(default)).strip().casefold()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if not value:
            return default
        if value in _YES:
            return True
        if value in _NO:
            return False
        language = _language()
        if language == "ar":
            print("اكتب y أو n (أو اضغط Enter للاختيار الافتراضي).")
        elif language == "zh":
            print("请输入 y 或 n（直接按 Enter 使用默认选项）。")
        else:
            print("Please enter y or n (or press Enter for the default).")


def apply_interactive_report_prompt(module: Any) -> None:
    """Wrap the shared parser so interactive CLI runs expose the report choice."""
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        explicit = any(
            value in {"--md-report", "--no-md-report"}
            for value in original[1:]
        )
        args = base_parse_args(env_file)

        # GUI workers, automation, and explicit CLI flags must never block on input.
        if explicit or bool(getattr(args, "non_interactive", False)):
            return args

        default = bool(getattr(args, "md_report", False))
        enabled = choose_report(default)
        os.environ[REPORT_ENV] = "true" if enabled else "false"
        setattr(args, "md_report", enabled)
        return args

    module.parse_args = parse_args
