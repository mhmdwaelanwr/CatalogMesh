#!/usr/bin/env python3
"""Beginner-friendly setup wizard for Product Sorter."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

from i18n import confirm_language, get_language, tr
from model_catalog import choose_from_list, default_model, models_for, refresh_catalog_for_keys
from secrets_store import SECRET_NAMES, save as save_secrets


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
MAIN_SCRIPT = ROOT / "product_sorter.py"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    return values


def clean(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("القيمة لا يمكن أن تحتوي على سطر جديد")
    return value.strip()


def build_env_text(values: dict[str, str]) -> str:
    keys = [f"{provider}_API_KEY_{index}" for provider in ("GEMINI","OPENAI","ANTHROPIC") for index in range(1, 5)]
    lines = ["# ملف إعداد Product Sorter - لا تشاركه بعد إضافة المفاتيح."]
    lines.extend(f"{name}={clean(values.get(name, ''))}" for name in keys)
    lines.extend([
        "",
        f"APP_LANGUAGE={clean(values.get('APP_LANGUAGE', ''))}",
        f"AI_PROVIDERS={clean(values.get('AI_PROVIDERS', 'gemini'))}",
        f"GEMINI_MODEL={clean(values.get('GEMINI_MODEL', 'gemini-3.6-flash'))}",
        f"OPENAI_MODEL={clean(values.get('OPENAI_MODEL', 'gpt-4.1-mini'))}",
        f"OPENAI_BASE_URL={clean(values.get('OPENAI_BASE_URL', ''))}",
        f"ANTHROPIC_MODEL={clean(values.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5'))}",
        f"COST_PER_REQUEST={clean(values.get('COST_PER_REQUEST', '0'))}",
        f"VALIDATE_KEYS={clean(values.get('VALIDATE_KEYS', 'true'))}",
        f"USE_KEYRING={clean(values.get('USE_KEYRING', 'false'))}",
        f"GEMINI_INPUT_COST_PER_MILLION={clean(values.get('GEMINI_INPUT_COST_PER_MILLION', '0'))}",
        f"GEMINI_OUTPUT_COST_PER_MILLION={clean(values.get('GEMINI_OUTPUT_COST_PER_MILLION', '0'))}",
        f"OPENAI_INPUT_COST_PER_MILLION={clean(values.get('OPENAI_INPUT_COST_PER_MILLION', '0'))}",
        f"OPENAI_OUTPUT_COST_PER_MILLION={clean(values.get('OPENAI_OUTPUT_COST_PER_MILLION', '0'))}",
        f"ANTHROPIC_INPUT_COST_PER_MILLION={clean(values.get('ANTHROPIC_INPUT_COST_PER_MILLION', '0'))}",
        f"ANTHROPIC_OUTPUT_COST_PER_MILLION={clean(values.get('ANTHROPIC_OUTPUT_COST_PER_MILLION', '0'))}",
        f"PRODUCT_SOURCE={clean(values.get('PRODUCT_SOURCE', ''))}",
        f"PRODUCT_OUTPUT={clean(values.get('PRODUCT_OUTPUT', ''))}",
        f"PRICES_FILE={clean(values.get('PRICES_FILE', ''))}",
        "",
        f"BATCH_SIZE={clean(values.get('BATCH_SIZE', '6'))}",
        f"CONFIDENCE={clean(values.get('CONFIDENCE', '0.75'))}",
        f"MAX_RETRIES={clean(values.get('MAX_RETRIES', '5'))}",
        f"PHOTO_LIMIT={clean(values.get('PHOTO_LIMIT', ''))}",
        "",
    ])
    return "\n".join(lines)


def save_env(values: dict[str, str], path: Path = ENV_FILE) -> None:
    values = dict(values)
    if values.get("USE_KEYRING", "").lower() in {"1", "true", "yes"} and save_secrets(values):
        for name in SECRET_NAMES:
            values[name] = ""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(build_env_text(values), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    os.chmod(path, 0o600)


def ask_text(label: str, current: str = "", required: bool = False) -> str:
    while True:
        shown_default = f" [{current}]" if current else ""
        value = input(f"{label}{shown_default}: ").strip()
        if value:
            return value
        if current:
            return current
        if not required:
            return ""
        print(tr("required"))


def ask_number(label: str, current: str, minimum: float, maximum: float,
               integer: bool = False) -> str:
    while True:
        value = ask_text(label, current, required=True)
        try:
            number = int(value) if integer else float(value)
            if minimum <= number <= maximum:
                return str(number)
        except ValueError:
            pass
        print(tr("number_range", minimum=minimum, maximum=maximum))


def ask_key(index: int, current: str, required: bool) -> str:
    while True:
        optional = f" - {tr('optional')}" if not required else ""
        hint = f" ({tr('keep_existing')})" if current else ""
        value = getpass.getpass(f"{tr('api_key', index=index)}{optional}{hint}: ").strip()
        if value:
            return value
        if current:
            return current
        if not required:
            return ""
        print(tr("first_key_required"))


def collect_settings(current: dict[str, str]) -> dict[str, str]:
    print(f"\n{tr('keys_private')}\n")
    values = dict(current)
    values["AI_PROVIDERS"] = ask_text(
        "AI providers order (gemini,openai,anthropic)",
        current.get("AI_PROVIDERS", "gemini"), True
    )
    selected={x.strip().lower() for x in values["AI_PROVIDERS"].split(",")}
    for provider in ("gemini","openai","anthropic"):
        if provider not in selected: continue
        print(f"\n{provider.upper()} keys (1 to 4):")
        for index in range(1,5):
            name=f"{provider.upper()}_API_KEY_{index}"
            values[name]=ask_key(index,current.get(name,""),required=(index==1))
    values["GEMINI_MODEL"] = choose_from_list("gemini", current.get("GEMINI_MODEL", default_model("gemini")), models_for("gemini"))
    values["OPENAI_MODEL"] = choose_from_list("openai", current.get("OPENAI_MODEL", default_model("openai")), models_for("openai"))
    values["OPENAI_BASE_URL"] = ask_text("OpenAI base URL (optional)", current.get("OPENAI_BASE_URL", ""))
    values["ANTHROPIC_MODEL"] = choose_from_list("anthropic", current.get("ANTHROPIC_MODEL", default_model("anthropic")), models_for("anthropic"))
    values["COST_PER_REQUEST"] = ask_number("Legacy estimated cost per request", current.get("COST_PER_REQUEST", "0"), 0, 1000)
    values["VALIDATE_KEYS"] = ask_text("Validate keys before processing? (true/false)", current.get("VALIDATE_KEYS", "true"), True)
    values["USE_KEYRING"] = ask_text("Store supported API keys in OS keyring? (true/false)", current.get("USE_KEYRING", "false"), True)
    values["GEMINI_INPUT_COST_PER_MILLION"] = ask_number("Gemini input cost per 1M tokens", current.get("GEMINI_INPUT_COST_PER_MILLION", "0"), 0, 100000)
    values["GEMINI_OUTPUT_COST_PER_MILLION"] = ask_number("Gemini output cost per 1M tokens", current.get("GEMINI_OUTPUT_COST_PER_MILLION", "0"), 0, 100000)
    values["OPENAI_INPUT_COST_PER_MILLION"] = ask_number("OpenAI input cost per 1M tokens", current.get("OPENAI_INPUT_COST_PER_MILLION", "0"), 0, 100000)
    values["OPENAI_OUTPUT_COST_PER_MILLION"] = ask_number("OpenAI output cost per 1M tokens", current.get("OPENAI_OUTPUT_COST_PER_MILLION", "0"), 0, 100000)
    values["ANTHROPIC_INPUT_COST_PER_MILLION"] = ask_number("Anthropic input cost per 1M tokens", current.get("ANTHROPIC_INPUT_COST_PER_MILLION", "0"), 0, 100000)
    values["ANTHROPIC_OUTPUT_COST_PER_MILLION"] = ask_number("Anthropic output cost per 1M tokens", current.get("ANTHROPIC_OUTPUT_COST_PER_MILLION", "0"), 0, 100000)
    values["PRODUCT_SOURCE"] = ask_text("Default product source folder", current.get("PRODUCT_SOURCE", ""))
    values["PRODUCT_OUTPUT"] = ask_text("Default product output folder", current.get("PRODUCT_OUTPUT", ""))
    values["PRICES_FILE"] = ask_text("Default prices file", current.get("PRICES_FILE", ""))
    values["BATCH_SIZE"] = ask_number("Batch size", current.get("BATCH_SIZE", "6"), 3, 8, integer=True)
    values["CONFIDENCE"] = ask_number("Confidence threshold", current.get("CONFIDENCE", "0.75"), 0, 1)
    values["MAX_RETRIES"] = ask_number("Max retries", current.get("MAX_RETRIES", "5"), 0, 20, integer=True)
    values["PHOTO_LIMIT"] = ask_text("Default photo limit (blank = all)", current.get("PHOTO_LIMIT", ""))
    return values


def main() -> int:
    current = read_env(ENV_FILE)
    language = confirm_language(current.get("APP_LANGUAGE") or get_language())
    current["APP_LANGUAGE"] = language
    refresh_catalog_for_keys(current)
    values = collect_settings(current)
    values["APP_LANGUAGE"] = language
    save_env(values)
    print(f"\n{tr('saved_to', path=ENV_FILE)}")
    print(tr("run_cli", command=f'python "{MAIN_SCRIPT}"'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
