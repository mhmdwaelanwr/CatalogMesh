"""Local-first Ollama vision integration and shared runtime performance tuning.

The adapter deliberately uses Ollama's HTTP API directly so Product Sorter does
not need an additional Python dependency.  It plugs into the existing provider
pool contract used by the CLI, GUI worker, benchmark instrumentation, and usage
reporting.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma4"
DEFAULT_KEEP_ALIVE = "10m"
DEFAULT_TIMEOUT = 300
DEFAULT_IMAGE_CACHE_ENTRIES = 24


def _base_url(value: str | None = None) -> str:
    return (value or os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL)).strip().rstrip("/")


def _timeout(value: int | None = None) -> int:
    if value is not None:
        return max(5, int(value))
    try:
        return max(5, int(os.getenv("OLLAMA_TIMEOUT", str(DEFAULT_TIMEOUT))))
    except ValueError:
        return DEFAULT_TIMEOUT


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        raw = ""
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                raw = str(data.get("error") or data.get("message") or raw)
        except (TypeError, ValueError):
            pass
    suffix = f": {raw[:600]}" if raw else ""
    return f"HTTP {exc.code} {exc.reason}{suffix}"


def _request_json(
    path: str,
    *,
    base_url: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    url = _base_url(base_url) + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout(timeout)) as response:
            decoded = json.loads(response.read())
            return decoded if isinstance(decoded, dict) else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama {_error_detail(exc)}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(
            f"Ollama is not reachable at {_base_url(base_url)}: {reason}. "
            "Start Ollama (for example `ollama serve`) and try again."
        ) from exc
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Ollama request failed at {_base_url(base_url)}: {exc}") from exc


def ollama_model_details(model: str, base_url: str | None = None) -> dict[str, Any]:
    if not model.strip():
        raise ValueError("An Ollama model name is required")
    return _request_json(
        "/api/show",
        base_url=base_url,
        payload={"model": model.strip(), "verbose": False},
        timeout=30,
    )


def discover_ollama_models(base_url: str | None = None, *, vision_only: bool = True) -> list[str]:
    """Return locally installed models, optionally filtering to vision-capable ones."""
    data = _request_json("/api/tags", base_url=base_url, timeout=20)
    names = []
    for item in data.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    if not vision_only:
        return sorted(names)

    vision_models: list[str] = []
    for name in names:
        try:
            details = ollama_model_details(name, base_url)
        except RuntimeError:
            continue
        capabilities = {str(value).lower() for value in details.get("capabilities", [])}
        if "vision" in capabilities:
            vision_models.append(name)
    return sorted(vision_models)


class OllamaVisionProvider:
    """Single local Ollama endpoint implementing the existing vision provider API."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.model = model.strip() or DEFAULT_MODEL
        self.base_url = _base_url(base_url)
        self.keep_alive = keep_alive.strip() or DEFAULT_KEEP_ALIVE
        self.timeout = _timeout(timeout)
        self.last_usage: dict[str, int] = {}
        self.last_metrics: dict[str, int] = {}

    def validate(self) -> tuple[bool, str]:
        try:
            details = ollama_model_details(self.model, self.base_url)
            capabilities = {str(value).lower() for value in details.get("capabilities", [])}
            if capabilities and "vision" not in capabilities:
                return False, f"model '{self.model}' is installed but does not advertise vision support"
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def generate(
        self,
        prompt: str,
        photos: list[Any],
        image_bytes: Callable[[Path], bytes],
    ) -> str:
        images = [
            base64.b64encode(image_bytes(photo.path)).decode("ascii")
            for photo in photos
        ]
        data = _request_json(
            "/api/chat",
            base_url=self.base_url,
            timeout=self.timeout,
            payload={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt, "images": images}],
                "stream": False,
                "format": "json",
                "keep_alive": self.keep_alive,
                "options": {"temperature": 0},
            },
        )
        self.last_usage = {
            "input_tokens": int(data.get("prompt_eval_count", 0) or 0),
            "output_tokens": int(data.get("eval_count", 0) or 0),
        }
        self.last_metrics = {
            "total_duration_ns": int(data.get("total_duration", 0) or 0),
            "load_duration_ns": int(data.get("load_duration", 0) or 0),
            "prompt_eval_duration_ns": int(data.get("prompt_eval_duration", 0) or 0),
            "eval_duration_ns": int(data.get("eval_duration", 0) or 0),
        }
        message = data.get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not str(content).strip():
            raise RuntimeError("Ollama returned an empty response")
        return str(content)


class OllamaProviderPool:
    """Provider-pool shaped wrapper so the shared engine needs no special branch."""

    name = "ollama"

    def __init__(self, model: str, base_url: str, keep_alive: str, timeout: int):
        self.model = model
        self.base_url = base_url
        self.index = 0
        self.last_usage: dict[str, int] = {}
        self.clients = [OllamaVisionProvider(model, base_url, keep_alive, timeout)]

    @property
    def client(self) -> OllamaVisionProvider:
        return self.clients[0]

    def rotate(self) -> bool:
        return False

    def add_key(self, key: str) -> None:  # pragma: no cover - engine compatibility only
        raise RuntimeError("Ollama is local and does not use API keys")

    def validate_all(self) -> list[tuple[bool, str]]:
        return [self.client.validate()]


def configured_ollama_provider() -> OllamaProviderPool:
    return OllamaProviderPool(
        model=os.getenv("OLLAMA_MODEL", DEFAULT_MODEL),
        base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
        keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE),
        timeout=_timeout(),
    )


def _requested_providers() -> list[str]:
    raw = os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini"))
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _install_image_cache(module: Any) -> None:
    """Cache encoded API JPEGs across overlap batches and provider fallbacks."""
    base_compress = module.compressed_image_bytes
    cache: OrderedDict[tuple[str, int, int], bytes] = OrderedDict()
    lock = threading.Lock()

    def compressed_image_bytes(path: Path) -> bytes:
        try:
            entries = int(os.getenv("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES", str(DEFAULT_IMAGE_CACHE_ENTRIES)))
        except ValueError:
            entries = DEFAULT_IMAGE_CACHE_ENTRIES
        if entries <= 0:
            return base_compress(path)
        stat = path.stat()
        key = (str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns))
        with lock:
            cached = cache.get(key)
            if cached is not None:
                cache.move_to_end(key)
                return cached
        encoded = base_compress(path)
        with lock:
            cache[key] = encoded
            cache.move_to_end(key)
            while len(cache) > entries:
                cache.popitem(last=False)
        return encoded

    module.compressed_image_bytes = compressed_image_bytes


def _install_cli_flags(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--local", action="store_true")
        parser.add_argument("--provider")
        parser.add_argument("--providers")
        parser.add_argument("--ollama-model")
        parser.add_argument("--ollama-url")
        parser.add_argument("--ollama-keep-alive")
        parser.add_argument("--ollama-timeout", type=int)
        known, remaining = parser.parse_known_args()
        if known.local:
            os.environ["AI_PROVIDERS"] = "ollama"
            os.environ["AI_PROVIDER"] = "ollama"
        elif known.providers:
            os.environ["AI_PROVIDERS"] = known.providers
            os.environ["AI_PROVIDER"] = known.providers.split(",", 1)[0].strip()
        elif known.provider:
            os.environ["AI_PROVIDERS"] = known.provider
            os.environ["AI_PROVIDER"] = known.provider
        if known.ollama_model:
            os.environ["OLLAMA_MODEL"] = known.ollama_model
        if known.ollama_url:
            os.environ["OLLAMA_BASE_URL"] = known.ollama_url
        if known.ollama_keep_alive:
            os.environ["OLLAMA_KEEP_ALIVE"] = known.ollama_keep_alive
        if known.ollama_timeout is not None:
            os.environ["OLLAMA_TIMEOUT"] = str(max(5, known.ollama_timeout))

        original_argv = sys.argv
        try:
            sys.argv = [original_argv[0], *remaining]
            return base_parse_args(env_file)
        finally:
            sys.argv = original_argv

    module.parse_args = parse_args


def apply_ollama_local(module: Any) -> None:
    """Install Ollama, offline behavior, CLI flags, and the shared image cache."""
    base_configured_rest_providers = module.configured_rest_providers
    base_require_internet = module.require_internet
    base_call_rest_pool = module.call_rest_pool

    def configured_rest_providers():
        providers = list(base_configured_rest_providers())
        if "ollama" in _requested_providers() and not any(p.name == "ollama" for p in providers):
            providers.append(configured_ollama_provider())
        return providers

    def require_internet(output: Path) -> bool:
        # A local-first operation must remain usable with Wi-Fi disconnected.
        # Cloud fallbacks will report their own connection error only if Ollama
        # itself cannot complete the batch.
        if "ollama" in _requested_providers():
            return True
        return base_require_internet(output)

    def call_rest_pool(pool: Any, photos: list[Any], catalog: str, max_retries: int,
                       live_progress: Any = None):
        if getattr(pool, "name", "") != "ollama":
            return base_call_rest_pool(pool, photos, catalog, max_retries, live_progress)

        failures = 0
        while True:
            try:
                result = module.call_rest_provider(pool.client, photos, catalog)
                pool.last_usage = dict(pool.client.last_usage)
                return result
            except Exception as exc:
                message = str(exc)
                upper = message.upper()
                terminal = any(marker in upper for marker in (
                    "404", "NOT FOUND", "DOES NOT ADVERTISE VISION", "DOES NOT SUPPORT VISION",
                    "UNKNOWN MODEL", "MODEL IS REQUIRED",
                ))
                if terminal or failures >= max_retries:
                    hint = (
                        f" Check `ollama list` and run `ollama pull {pool.model}` if the model "
                        "is not installed."
                    )
                    raise RuntimeError(f"Ollama local inference failed: {message}.{hint}") from exc
                failures += 1
                delay = min(15, 2 ** failures)
                note = f"Ollama local error; retrying in {delay}s ({failures}/{max_retries})"
                live_progress.note(note) if live_progress else print(note)
                time.sleep(delay)

    module.configured_rest_providers = configured_rest_providers
    module.require_internet = require_internet
    module.call_rest_pool = call_rest_pool
    _install_image_cache(module)
    _install_cli_flags(module)
