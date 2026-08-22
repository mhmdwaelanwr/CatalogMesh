"""Provider model catalog with live, credential-scoped discovery and JSON fallback."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CATALOG_FILE = ROOT / "provider_models.json"
PROVIDERS = ("gemini", "openai", "anthropic")
ENV_MODEL_NAMES = {
    "gemini": "GEMINI_MODEL",
    "openai": "OPENAI_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
}


def load_catalog(path: Path = CATALOG_FILE) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("providers"), dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"schema_version": 1, "providers": {name: {"default": "", "models": []} for name in PROVIDERS}}


def models_for(provider: str, path: Path = CATALOG_FILE) -> list[str]:
    entry = load_catalog(path).get("providers", {}).get(provider.lower(), {})
    models = entry.get("models", [])
    return sorted({str(model).strip() for model in models if str(model).strip()})


def default_model(provider: str, path: Path = CATALOG_FILE) -> str:
    entry = load_catalog(path).get("providers", {}).get(provider.lower(), {})
    return str(entry.get("default", "")).strip()


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def discover_models(provider: str, api_key: str, base_url: str = "") -> list[str]:
    """Return every model visible to this credential; never stores or returns the key."""
    provider = provider.lower().strip()
    if not api_key:
        raise ValueError("An API key is required to download the provider model list")
    if provider == "gemini":
        data = _get_json(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
            {"x-goog-api-key": api_key},
        )
        result = []
        for item in data.get("models", []):
            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                result.append(str(item.get("name", "")).removeprefix("models/"))
    elif provider == "openai":
        url = (base_url.rstrip("/") or "https://api.openai.com/v1") + "/models"
        data = _get_json(url, {"Authorization": f"Bearer {api_key}"})
        result = [str(item.get("id", "")) for item in data.get("data", [])]
    elif provider == "anthropic":
        data = _get_json(
            "https://api.anthropic.com/v1/models?limit=1000",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        result = [str(item.get("id", "")) for item in data.get("data", [])]
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    models = sorted({model.strip() for model in result if model.strip()})
    if not models:
        raise RuntimeError(f"{provider} returned no available models")
    return models


def refresh_catalog(provider: str, api_key: str, base_url: str = "", path: Path = CATALOG_FILE) -> list[str]:
    models = discover_models(provider, api_key, base_url)
    data = load_catalog(path)
    entry = data.setdefault("providers", {}).setdefault(provider, {})
    previous_default = str(entry.get("default", ""))
    entry["models"] = models
    entry["default"] = previous_default if previous_default in models else models[0]
    entry["source"] = "live_api"
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return models


def choose_from_list(provider: str, current: str, models: list[str]) -> str:
    ordered = list(models)
    if current and current not in ordered:
        ordered.insert(0, current)
    if not ordered:
        return current
    print(f"\nAvailable {provider.title()} models:")
    for index, model in enumerate(ordered, 1):
        marker = " (current)" if model == current else ""
        print(f"[{index}] {model}{marker}")
    print(f"[{len(ordered) + 1}] Enter a model name manually")
    while True:
        raw = input(f"Choose model [1-{len(ordered) + 1}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(ordered):
            return ordered[int(raw) - 1]
        if raw == str(len(ordered) + 1):
            manual = input("Model name: ").strip()
            if manual:
                return manual
        print("Invalid model choice.")
