#!/usr/bin/env python3
"""Opt-in live credential check. Never prints keys or sends product images."""

from providers import configured_rest_providers
from sorter_core import DEFAULT_ENV_FILE, load_api_keys, load_env_file, validate_gemini_key


def _safe_reason(message: str) -> str:
    """Keep live-smoke diagnostics useful without echoing credentials."""
    text = " ".join(str(message or "unknown error").split())
    return text[:600]


def main() -> int:
    load_env_file(DEFAULT_ENV_FILE)
    failures = 0
    gemini = load_api_keys()
    rest = configured_rest_providers()

    for i, key in enumerate(gemini, 1):
        ok, reason = validate_gemini_key(key)
        status = "OK" if ok else f"FAILED — {_safe_reason(reason)}"
        print(f"gemini key {i}: {status}")
        failures += not ok

    for provider in rest:
        for i, (ok, reason) in enumerate(provider.validate_all(), 1):
            status = "OK" if ok else f"FAILED — {_safe_reason(reason)}"
            print(f"{provider.name} key {i}: {status}")
            failures += not ok

    if not gemini and not rest:
        print("No live API keys configured.")
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
