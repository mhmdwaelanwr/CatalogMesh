from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from model_catalog import default_model

SUPPORTED_REST_PROVIDERS = ("openai", "anthropic")


def load_provider_keys(name: str) -> list[str]:
    """Load one to four unique keys, retaining the legacy unnumbered variable."""
    prefix = name.upper() + "_API_KEY"
    candidates = [os.getenv(f"{prefix}_{i}", "").strip() for i in range(1, 5)]
    candidates.append(os.getenv(prefix, "").strip())
    result = []
    for key in candidates:
        if key and key not in result:
            result.append(key)
    return result[:4]


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    """Return a useful provider error without exposing request headers or credentials."""
    detail = ""
    try:
        raw = exc.read().decode("utf-8", errors="replace").strip()
        if raw:
            try:
                data = json.loads(raw)
                error = data.get("error", data) if isinstance(data, dict) else data
                if isinstance(error, dict):
                    detail = str(
                        error.get("message")
                        or error.get("type")
                        or error.get("code")
                        or raw
                    )
                else:
                    detail = str(error)
            except (ValueError, TypeError):
                detail = raw
    except Exception:
        detail = ""
    suffix = f": {detail[:600]}" if detail else ""
    return f"HTTP {exc.code} {exc.reason}{suffix}"


def _post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int = 120,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_http_error_message(exc)) from exc


def _jpeg_data(path: Path, image_bytes: Callable[[Path], bytes]) -> str:
    return base64.b64encode(image_bytes(path)).decode()


class RestVisionProvider:
    def __init__(self, name: str, key: str, model: str, base_url: str = ""):
        self.name = name
        self.key = key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.last_usage = {}

    def validate(self) -> tuple[bool, str]:
        try:
            if self.name == "openai":
                req = urllib.request.Request(
                    (self.base_url or "https://api.openai.com/v1") + "/models",
                    headers={"Authorization": f"Bearer {self.key}"},
                )
            else:
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": self.key,
                        "anthropic-version": "2023-06-01",
                    },
                )
            with urllib.request.urlopen(req, timeout=15):
                pass
            return True, "ok"
        except urllib.error.HTTPError as exc:
            return False, _http_error_message(exc)
        except Exception as exc:
            return False, str(exc)

    def generate(
        self,
        prompt: str,
        photos: list[Any],
        image_bytes: Callable[[Path], bytes],
    ) -> str:
        if self.name == "openai":
            content = [{"type": "text", "text": prompt}]
            content += [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,"
                        + _jpeg_data(photo.path, image_bytes)
                    },
                }
                for photo in photos
            ]
            data = _post(
                (self.base_url or "https://api.openai.com/v1") + "/chat/completions",
                {"Authorization": f"Bearer {self.key}"},
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "response_format": {"type": "json_object"},
                },
            )
            usage = data.get("usage", {})
            self.last_usage = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            }
            return data["choices"][0]["message"]["content"]

        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": _jpeg_data(photo.path, image_bytes),
                },
            }
            for photo in photos
        ]
        content.append({"type": "text", "text": prompt})
        # Do not send sampling parameters here. Newer Claude models such as
        # Claude Sonnet 5 reject non-default temperature/top_p/top_k values.
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": content}],
            },
        )
        self.last_usage = data.get("usage", {})
        return "".join(
            block.get("text", "")
            for block in data["content"]
            if block.get("type") == "text"
        )


class RestProviderPool:
    def __init__(self, name: str, keys: list[str], model: str, base_url: str = ""):
        self.name = name
        self.model = model
        self.base_url = base_url
        self.index = 0
        self.last_usage = {}
        self.clients = [RestVisionProvider(name, key, model, base_url) for key in keys]

    @property
    def client(self) -> RestVisionProvider:
        return self.clients[self.index]

    def rotate(self) -> bool:
        if len(self.clients) < 2:
            return False
        self.index = (self.index + 1) % len(self.clients)
        return True

    def add_key(self, key: str) -> None:
        self.clients.append(RestVisionProvider(self.name, key, self.model, self.base_url))
        self.index = len(self.clients) - 1

    def validate_all(self) -> list[tuple[bool, str]]:
        return [client.validate() for client in self.clients]


def configured_rest_providers() -> list[RestProviderPool]:
    wanted = [
        item.strip().lower()
        for item in os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini")).split(",")
    ]
    result = []
    for name in wanted:
        keys = load_provider_keys(name) if name in SUPPORTED_REST_PROVIDERS else []
        if name == "openai" and keys:
            result.append(
                RestProviderPool(
                    "openai",
                    keys,
                    os.getenv(
                        "OPENAI_MODEL",
                        default_model("openai") or "gpt-4.1-mini",
                    ),
                    os.getenv("OPENAI_BASE_URL", ""),
                )
            )
        if name == "anthropic" and keys:
            result.append(
                RestProviderPool(
                    "anthropic",
                    keys,
                    os.getenv(
                        "ANTHROPIC_MODEL",
                        default_model("anthropic") or "claude-sonnet-5",
                    ),
                )
            )
    return result
