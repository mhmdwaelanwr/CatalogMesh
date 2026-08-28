"""Canonical provider selection shared by CLI and desktop GUI."""

from __future__ import annotations

import difflib
import os
import sys
from typing import Any

SUPPORTED_PROVIDERS = ("gemini", "openai", "anthropic")
_PROVIDER_ALIASES = {
    "gemeni": "gemini",
}


class ProviderSelectionError(ValueError):
    """Raised when a configured provider name cannot be resolved safely."""


def normalize_provider_sequence(raw: str | None) -> tuple[list[str], list[tuple[str, str]]]:
    """Return canonical provider names and any safe typo corrections.

    Provider names are case-insensitive, duplicates are removed while preserving
    order, and the historically observed ``gemeni`` typo is corrected to
    ``gemini``. Other unknown names fail with a close-match suggestion instead of
    silently leaving the sorter with no usable provider.
    """

    text = (raw or "").strip()
    items = [item.strip().lower() for item in text.split(",") if item.strip()]
    if not items:
        items = ["gemini"]

    result: list[str] = []
    corrections: list[tuple[str, str]] = []
    for original in items:
        name = _PROVIDER_ALIASES.get(original, original)
        if name != original:
            corrections.append((original, name))
        if name not in SUPPORTED_PROVIDERS:
            match = difflib.get_close_matches(name, SUPPORTED_PROVIDERS, n=1, cutoff=0.55)
            suffix = f" Did you mean '{match[0]}'?" if match else ""
            raise ProviderSelectionError(
                f"Unknown provider '{original}'. Supported providers: "
                f"{', '.join(SUPPORTED_PROVIDERS)}.{suffix}"
            )
        if name not in result:
            result.append(name)
    return result, corrections


def canonical_provider_string(raw: str | None) -> tuple[str, list[tuple[str, str]]]:
    providers, corrections = normalize_provider_sequence(raw)
    return ",".join(providers), corrections


def normalize_provider_environment(*, announce: bool = True) -> str:
    raw = os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini"))
    canonical, corrections = canonical_provider_string(raw)
    os.environ["AI_PROVIDERS"] = canonical
    os.environ["AI_PROVIDER"] = canonical.split(",", 1)[0]
    if announce:
        for old, new in corrections:
            print(
                f"Warning: corrected provider name '{old}' to '{new}'.",
                file=sys.stderr,
            )
    return canonical


def apply_provider_selection(module: Any) -> None:
    """Normalize provider configuration before provider pools are constructed."""

    base_load_env_file = module.load_env_file
    base_main = module.main

    def load_env_file(path):
        loaded = base_load_env_file(path)
        normalize_provider_environment()
        return loaded

    def main() -> int:
        try:
            # Covers GUI/process environment. ``load_env_file`` repeats the
            # normalization after .env is loaded for source/CLI launches.
            normalize_provider_environment()
            return base_main()
        except ProviderSelectionError as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2

    module.load_env_file = load_env_file
    module.main = main
