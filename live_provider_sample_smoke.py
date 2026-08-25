#!/usr/bin/env python3
"""Opt-in live vision smoke test using two generated, non-sensitive images.

The script never prints API keys and does not use real product photos. It makes one
small vision request per requested provider, then verifies that both generated
filenames are represented in the normalized response.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from model_catalog import default_model
from providers import configured_rest_providers
from sorter_core import GeminiClientPool, Photo, call_gemini, call_rest_pool, load_api_keys

SUPPORTED = ("gemini", "openai", "anthropic")


def requested_providers() -> list[str]:
    raw = os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini"))
    requested: list[str] = []
    for item in raw.split(","):
        name = item.strip().lower()
        if name in SUPPORTED and name not in requested:
            requested.append(name)
    return requested


def redact_error(exc: Exception) -> str:
    text = str(exc)
    for name, value in os.environ.items():
        if "API_KEY" in name and value:
            text = text.replace(value, "[REDACTED]")
    return text[:700]


def make_samples(root: Path) -> list[Photo]:
    root.mkdir(parents=True, exist_ok=True)
    created = datetime.now()
    paths: list[Path] = []

    for index, view in enumerate(("front", "back")):
        path = root / f"synthetic_product_{view}.jpg"
        image = Image.new("RGB", (640, 480), "white")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((150, 95, 490, 385), radius=28, fill=(48, 92, 170), outline="black", width=5)
        if view == "front":
            draw.rectangle((245, 175, 395, 295), fill=(220, 230, 245), outline="black", width=4)
            draw.ellipse((300, 315, 340, 355), fill=(35, 35, 35))
        else:
            draw.rectangle((210, 145, 430, 330), fill=(70, 105, 175), outline="black", width=4)
            for x in (245, 315, 385):
                draw.ellipse((x, 350, x + 22, 372), fill=(28, 28, 28))
        image.save(path, "JPEG", quality=88, optimize=True)
        paths.append(path)

    return [Photo(path, created + timedelta(seconds=index)) for index, path in enumerate(paths)]


def verify_response(provider: str, response: dict[str, Any], photos: list[Photo]) -> None:
    items = response.get("items")
    if not isinstance(items, list):
        raise RuntimeError(f"{provider} returned no normalized item list")
    expected = {photo.path.name for photo in photos}
    received = {str(item.get("filename", "")) for item in items if isinstance(item, dict)}
    if not expected.issubset(received):
        missing = ", ".join(sorted(expected - received))
        raise RuntimeError(f"{provider} normalized response is missing: {missing}")


def run_provider(name: str, photos: list[Photo]) -> None:
    if name == "gemini":
        keys = load_api_keys()
        if not keys:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        pool = GeminiClientPool(keys)
        model = os.getenv("GEMINI_MODEL", default_model("gemini") or "gemini-3.6-flash")
        response = call_gemini(pool, model, photos, "", max_retries=0)
    else:
        pools = {pool.name: pool for pool in configured_rest_providers()}
        pool = pools.get(name)
        if pool is None:
            raise RuntimeError(f"{name.upper()}_API_KEY is not configured")
        response = call_rest_pool(pool, photos, "", max_retries=0)
    verify_response(name, response, photos)


def main() -> int:
    requested = requested_providers()
    if not requested:
        print("No supported providers requested.")
        return 2

    failures = 0
    with tempfile.TemporaryDirectory(prefix="product-sorter-provider-smoke-") as tmp:
        photos = make_samples(Path(tmp))
        print(f"Generated {len(photos)} synthetic, non-sensitive JPEG samples.")
        for provider in requested:
            try:
                run_provider(provider, photos)
                print(f"{provider}: LIVE SAMPLE OK")
            except Exception as exc:  # live provider failures must not expose secrets
                failures += 1
                print(f"{provider}: LIVE SAMPLE FAILED — {redact_error(exc)}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
