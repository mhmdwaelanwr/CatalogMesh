"""Startup API-key validation hardening.

The compatibility engine already validates configured keys, but historically it
only printed failures and still left those keys in the active provider pools.
This extension keeps the existing CLI output while removing keys that are
definitively invalid before any product image is sent to a provider.

Transient validation failures (timeouts, connectivity failures, rate limits,
server errors) are deliberately *not* treated as proof that a key is invalid.
Those keys stay available so the normal connectivity/retry path can decide what
to do.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any


_LOCAL = threading.local()


def _validation_enabled() -> bool:
    if "--validate-keys" in sys.argv:
        return True
    return os.getenv("VALIDATE_KEYS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _requested_providers() -> list[str]:
    raw = os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini"))
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _definitively_invalid(detail: str) -> bool:
    """Return True only for failures that strongly indicate bad credentials."""
    text = detail.upper()
    invalid_markers = (
        "HTTP 400",
        "HTTP ERROR 400",
        "HTTP 401",
        "HTTP ERROR 401",
        "HTTP 403",
        "HTTP ERROR 403",
        "API_KEY_INVALID",
        "API KEY NOT VALID",
        "INVALID API KEY",
        "INVALID_API_KEY",
        "UNAUTHENTICATED",
        "INVALID X-API-KEY",
    )
    return any(marker in text for marker in invalid_markers)


def _inconclusive_detail(detail: str) -> str:
    suffix = "validation inconclusive; key kept for normal retry handling"
    return f"{detail} ({suffix})" if detail else suffix


def apply_key_validation_hardening(module: Any) -> None:
    """Filter definitively invalid provider keys during real ``main()`` runs."""

    base_main = module.main
    base_load_api_keys = module.load_api_keys
    base_validate_gemini_key = module.validate_gemini_key
    base_gemini_pool = module.GeminiClientPool
    base_configured_rest_providers = module.configured_rest_providers

    def _active() -> bool:
        return bool(getattr(_LOCAL, "active", False))

    def _cache() -> dict[str, tuple[bool, str]]:
        cache = getattr(_LOCAL, "gemini_validation", None)
        if cache is None:
            cache = {}
            _LOCAL.gemini_validation = cache
        return cache

    def load_api_keys() -> list[str]:
        keys = base_load_api_keys()
        # Do not validate or construct Gemini clients when Gemini is not part of
        # the requested provider chain. Direct helper calls outside main keep the
        # original behavior for compatibility/tests.
        if _active() and "gemini" not in _requested_providers():
            return []
        return keys

    def validate_gemini_key(key: str) -> tuple[bool, str]:
        if _active() and _validation_enabled() and key in _cache():
            return _cache()[key]
        return base_validate_gemini_key(key)

    class ValidatingGeminiClientPool(base_gemini_pool):
        def __init__(self, keys: list[str]):
            if not (_active() and _validation_enabled()):
                super().__init__(keys)
                return

            usable: list[str] = []
            results: list[tuple[str, bool, str, bool]] = []
            for key in keys:
                ok, detail = base_validate_gemini_key(key)
                rejected = (not ok) and _definitively_invalid(detail)
                cached = (ok, detail if ok or rejected else _inconclusive_detail(detail))
                _cache()[key] = cached
                results.append((key, ok, cached[1], rejected))
                if not rejected:
                    usable.append(key)

            # If every configured Gemini key is definitively invalid, main() will
            # exit before its legacy validation-print loop. Emit the failures here
            # so the user still knows exactly why no provider is usable.
            if keys and not usable:
                for index, (_, ok, detail, _) in enumerate(results, 1):
                    if not ok:
                        print(f"gemini key {index}: FAILED {detail} (rejected)")

            super().__init__(usable)

        def __bool__(self) -> bool:
            return bool(self.clients)

    def configured_rest_providers() -> list[Any]:
        pools = base_configured_rest_providers()
        if not (_active() and _validation_enabled()):
            return pools

        usable_pools: list[Any] = []
        for pool in pools:
            original_clients = list(pool.clients)
            results = pool.validate_all()
            kept_clients: list[Any] = []
            kept_results: list[tuple[bool, str]] = []

            for index, (client, result) in enumerate(zip(original_clients, results), 1):
                ok, detail = result
                rejected = (not ok) and _definitively_invalid(detail)
                if rejected:
                    print(f"{pool.name} key {index}: FAILED {detail} (rejected)")
                    continue
                kept_clients.append(client)
                kept_results.append(
                    (ok, detail if ok else _inconclusive_detail(detail))
                )

            pool.clients = kept_clients
            pool.index = 0
            # Avoid a second network validation in the compatibility engine while
            # preserving its normal status-printing loop for retained keys.
            pool.validate_all = lambda results=tuple(kept_results): list(results)
            if kept_clients:
                usable_pools.append(pool)

        return usable_pools

    def main() -> int:
        previous_active = getattr(_LOCAL, "active", None)
        previous_cache = getattr(_LOCAL, "gemini_validation", None)
        _LOCAL.active = True
        _LOCAL.gemini_validation = {}
        try:
            return base_main()
        finally:
            if previous_active is None:
                try:
                    del _LOCAL.active
                except AttributeError:
                    pass
            else:
                _LOCAL.active = previous_active

            if previous_cache is None:
                try:
                    del _LOCAL.gemini_validation
                except AttributeError:
                    pass
            else:
                _LOCAL.gemini_validation = previous_cache

    module.load_api_keys = load_api_keys
    module.validate_gemini_key = validate_gemini_key
    module.GeminiClientPool = ValidatingGeminiClientPool
    module.configured_rest_providers = configured_rest_providers
    module.main = main
