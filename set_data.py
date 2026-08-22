#!/usr/bin/env python3
"""Beginner-friendly setup wizard for Product Sorter."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

from i18n import confirm_language, get_language, tr
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
        f"GEMINI_MODEL={clean(values.get('GEMINI_MODEL', 'gemini-2.5-flash'))}",
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
        for index in range(1, 5):
            name = f"{provider.upper()}_API_KEY_{index}"
            legacy=current.get(f"{provider.upper()}_API_KEY","") if index==1 else ""
            values[name] = ask_key(index, current.get(name, "") or legacy, required=index == 1)
    if "openai" in selected:
        values["OPENAI_MODEL"] = ask_text("OpenAI model", current.get("OPENAI_MODEL", "gpt-4.1-mini"), True)
        values["OPENAI_BASE_URL"] = ask_text("OpenAI-compatible base URL (optional)", current.get("OPENAI_BASE_URL", ""))
    if "anthropic" in selected:
        values["ANTHROPIC_MODEL"] = ask_text("Anthropic model", current.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"), True)

    source = ask_text(tr("source_path"), current.get("PRODUCT_SOURCE", ""), True)
    values["PRODUCT_SOURCE"] = str(Path(source).expanduser())
    default_output = current.get("PRODUCT_OUTPUT", "")
    if not default_output:
        default_output = str(Path(source).expanduser().parent / "Sorted_Products")
    values["PRODUCT_OUTPUT"] = ask_text(tr("output_path"), default_output, True)
    values["PRICES_FILE"] = ask_text(
        tr("prices_path"), current.get("PRICES_FILE", "")
    )
    values["GEMINI_MODEL"] = ask_text(
        tr("model"), current.get("GEMINI_MODEL", "gemini-2.5-flash"), True
    )
    values["BATCH_SIZE"] = ask_number(
        tr("batch_size"), current.get("BATCH_SIZE", "6"), 3, 8, True
    )
    values["CONFIDENCE"] = ask_number(
        tr("confidence"), current.get("CONFIDENCE", "0.75"), 0, 1
    )
    values["MAX_RETRIES"] = ask_number(
        tr("retries"), current.get("MAX_RETRIES", "5"), 0, 20, True
    )
    values["COST_PER_REQUEST"] = ask_number("Estimated cost per API request", current.get("COST_PER_REQUEST", "0"), 0, 1000)
    values["VALIDATE_KEYS"] = ask_text("Validate API keys at startup (true/false)", current.get("VALIDATE_KEYS", "true"), True)
    values["USE_KEYRING"] = ask_text("Store API keys in OS keyring (true/false)", current.get("USE_KEYRING", "false"), True)
    values["PHOTO_LIMIT"] = ask_text(
        tr("photo_limit"), current.get("PHOTO_LIMIT", "")
    )
    if values["PHOTO_LIMIT"] and not values["PHOTO_LIMIT"].isdigit():
        print(tr("bad_photo_limit"))
        values["PHOTO_LIMIT"] = ""
    return values


def run_main(gui: bool = False) -> int:
    print(f"\n{tr('running')}\n")
    script = ROOT / ("product_sorter_gui.py" if gui else "product_sorter.py")
    return subprocess.run([sys.executable, str(script)], cwd=ROOT).returncode


def choose_interface_and_run() -> int:
    print("\n[1] GUI / Tkinter")
    print("[2] CLI / Terminal")
    choice = menu(tr("choose_numbers", choices="1 / 2"), {"1", "2"})
    return run_main(gui=choice == "1")


def menu(prompt: str, valid: set[str]) -> str:
    while True:
        choice = input(prompt).strip()
        if choice in valid:
            return choice
        print(tr("invalid"))


def main() -> int:
    current = read_env(ENV_FILE)
    if current.get("APP_LANGUAGE"):
        os.environ.setdefault("APP_LANGUAGE", current["APP_LANGUAGE"])
    language = confirm_language()
    print("=" * 55)
    print(tr("setup_title"))
    print("=" * 55)
    if ENV_FILE.is_file():
        print(f"\n{tr('existing_env')}")
        print(f"[1] {tr('edit_env')}")
        print(f"[2] {tr('run_existing')}")
        print(f"[3] {tr('new_env')}")
        print(f"[4] {tr('exit')}")
        choice = menu(tr("choose_numbers", choices="1 / 2 / 3 / 4"), {"1", "2", "3", "4"})
        if choice == "2":
            return choose_interface_and_run()
        if choice == "3":
            current = {}
        if choice == "4":
            return 0

    values = collect_settings(current)
    values["APP_LANGUAGE"] = language
    print(f"\n{tr('what_next')}")
    print(f"[1] {tr('save_only')}")
    print(f"[2] {tr('save_run')}")
    print(f"[3] {tr('cancel')}")
    choice = menu(tr("choose_numbers", choices="1 / 2 / 3"), {"1", "2", "3"})
    if choice == "3":
        print(tr("cancelled"))
        return 0
    save_env(values)
    print(tr("saved", path=ENV_FILE))
    if choice == "2":
        return choose_interface_and_run()
    print(tr("run_later"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
