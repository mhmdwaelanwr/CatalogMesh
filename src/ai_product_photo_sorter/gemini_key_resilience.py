"""Resilient Gemini key failover for long-running photo sorting jobs.

The compatibility engine already rotates keys for quota exhaustion.  This module
adds a narrower failure mode: credentials whose Google Cloud project cannot use
the Gemini API at all (for example SERVICE_DISABLED) must not abort an otherwise
healthy run when another configured key is available.

Only explicit credential/project markers are handled here.  A generic 403 stays
terminal so permission, model, and configuration bugs are never hidden behind
blind key rotation.
"""

from __future__ import annotations

from functools import wraps
from typing import Any


_KEY_FAILURE_MARKERS = (
    "SERVICE_DISABLED",
    "API_KEY_INVALID",
    "API KEY NOT VALID",
    "API KEY INVALID",
    "API_KEY_SERVICE_BLOCKED",
    "API_KEY_HTTP_REFERRER_BLOCKED",
    "API_KEY_IP_ADDRESS_BLOCKED",
    "API_KEY_ANDROID_APP_BLOCKED",
    "API_KEY_IOS_APP_BLOCKED",
)


def _key_failure_reason(error: BaseException) -> str:
    """Return a safe reason label for explicit key/project failures only."""

    message = str(error).upper()
    for marker in _KEY_FAILURE_MARKERS:
        if marker in message:
            return marker
    return ""


def _drop_current_client(pool: Any) -> int | None:
    """Remove the failed client and select the next client without exposing keys.

    Returns the number of configured clients left, or ``None`` when the supplied
    pool does not expose the normal mutable ``clients``/``index`` interface.
    """

    clients = getattr(pool, "clients", None)
    if not isinstance(clients, list) or not clients:
        return None

    try:
        index = int(getattr(pool, "index", 0))
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(clients):
        return None

    del clients[index]
    if clients:
        # Removing a middle entry naturally selects the following client at the
        # same index; removing the final entry wraps to the first client.
        pool.index = index % len(clients)
    else:
        pool.index = 0
    return len(clients)


def _note(live_progress: Any, message: str) -> None:
    if live_progress is not None:
        live_progress.note(message)
    else:
        print(message)


def apply_gemini_key_resilience(module: Any) -> None:
    """Patch ``call_gemini`` so explicitly unusable keys fail over safely."""

    original = module.call_gemini
    if getattr(original, "_product_sorter_key_resilience", False):
        return

    @wraps(original)
    def resilient_call_gemini(
        pool: Any,
        model: str,
        photos: list[Any],
        catalog: str,
        max_retries: int,
        live_progress: Any = None,
    ) -> dict[str, Any]:
        while True:
            try:
                return original(pool, model, photos, catalog, max_retries, live_progress)
            except RuntimeError as exc:
                reason = _key_failure_reason(exc)
                if not reason:
                    raise

                remaining = _drop_current_client(pool)
                if remaining is None:
                    # Unknown pool shape: preserve the engine's original failure
                    # instead of guessing and potentially retrying forever.
                    raise

                if remaining:
                    _note(
                        live_progress,
                        "Gemini key is unusable for this run "
                        f"({reason}); switching automatically to another configured "
                        f"key ({remaining} remaining).",
                    )
                    continue

                new_key = module.request_new_api_key(live_progress, "Gemini")
                if not new_key:
                    raise RuntimeError(
                        "All configured Gemini keys are unusable for this run. Progress "
                        "is saved; enable the Gemini API for the affected Google Cloud "
                        "project or add a working Gemini API key, then run the same "
                        "command again to continue."
                    ) from exc

                pool.add_key(new_key)
                _note(live_progress, "New Gemini key accepted; retrying the current batch.")

    resilient_call_gemini._product_sorter_key_resilience = True
    module.call_gemini = resilient_call_gemini
