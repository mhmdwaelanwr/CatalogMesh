#!/usr/bin/env python3
"""Opt-in live credential check. Never prints keys or sends product images."""

import os
import re

from providers import configured_rest_providers
from sorter_core import DEFAULT_ENV_FILE, load_api_keys, load_env_file, validate_gemini_key

_SECRET_PATTERNS = (
    (re.compile(r"(?i)(api\s*key(?:\s+provided)?\s*:\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_.*-]{6,}\b"), "sk-[REDACTED]"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{8,}\b"), "AIza[REDACTED]"),
)


def safe_reason(message: str) -> str:
    """Return useful live-smoke diagnostics without echoing credential fragments."""
    text = " ".join(str(message or "unknown error").split())
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text[:600]


def requested_providers() -> list[str]:
    raw = os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini"))
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def main() -> int:
    load_env_file(DEFAULT_ENV_FILE)
    failures = 0
    checked = 0
    requested = requested_providers()

    if "gemini" in requested:
        for i, key in enumerate(load_api_keys(), 1):
            ok, reason = validate_gemini_key(key)
            status = "OK" if ok else f"FAILED — {safe_reason(reason)}"
            print(f"gemini key {i}: {status}")
            failures += not ok
            checked += 1

    for provider in configured_rest_providers():
        for i, (ok, reason) in enumerate(provider.validate_all(), 1):
            status = "OK" if ok else f"FAILED — {safe_reason(reason)}"
            print(f"{provider.name} key {i}: {status}")
            failures += not ok
            checked += 1

    if not checked:
        print("No live API keys configured for the requested providers.")
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
