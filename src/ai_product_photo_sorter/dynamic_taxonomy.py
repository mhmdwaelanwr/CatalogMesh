"""AI-managed category taxonomy for long-running product photo jobs.

The base engine historically constrained every classification to a fixed list.
For real retail catalogs that turns perfectly understandable products into
``other`` simply because their type was not predeclared. This layer keeps the
same classification API call, but lets the model establish concise product-type
categories from the images it actually sees and then feeds those learned
categories back into later batches for consistency.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


CATEGORY_REGISTRY_NAME = "category_registry.json"
MAX_CATEGORY_LENGTH = 48
MAX_PROMPT_CATEGORIES = 120


def category_slug(value: Any) -> str:
    """Normalize an AI category into a portable lowercase folder slug."""

    text = str(value or "").strip().casefold().replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if slug in {"", "unknown", "uncategorized", "misc", "miscellaneous"}:
        return "other"
    return slug[:MAX_CATEGORY_LENGTH].rstrip("_") or "other"


def _parse_response(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    return json.loads(text)


def _register_items(module: Any, observed: set[str], items: list[dict[str, Any]]) -> None:
    for item in items:
        category = category_slug(item.get("category", "other"))
        item["category"] = category
        module.CATEGORIES.add(category)
        if category != "other":
            observed.add(category)


def _normalize_response(
    module: Any,
    observed: set[str],
    raw: str,
    photos: list[Any],
) -> dict[str, Any]:
    """Validate the legacy response shape without restricting category names."""

    data = _parse_response(raw)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items")
    else:
        raise ValueError("AI response must be a JSON object or list")

    if not isinstance(items, list) or len(items) != len(photos):
        raise ValueError("AI response did not contain one item per image")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("AI response items must be JSON objects")

    expected = [photo.path.name for photo in photos]
    received = [str(item.get("filename", "")) for item in items]
    if received != expected:
        raise ValueError(f"AI returned unexpected filename order: {received}")

    for index, item in enumerate(items):
        item["same_product_as_previous"] = (
            bool(item.get("same_product_as_previous", False)) if index else False
        )
        category = category_slug(item.get("category", "other"))
        item["category"] = category
        module.CATEGORIES.add(category)
        if category != "other":
            observed.add(category)

        try:
            item["confidence"] = max(
                0.0, min(1.0, float(item.get("confidence", 0)))
            )
        except (TypeError, ValueError):
            item["confidence"] = 0.0

        for field in ("view", "brand", "model", "catalog_match", "reason"):
            item[field] = str(item.get(field, "")).strip()

    return {"items": items}


def _prompt_for(
    photos: list[Any],
    catalog: str,
    observed: set[str],
) -> str:
    listing = "\n".join(
        f"Image {index}: {photo.path.name}, captured {photo.taken_at.isoformat(sep=' ')}"
        for index, photo in enumerate(photos, 1)
    )
    catalog_text = f"\nPossible catalog rows:\n{catalog}" if catalog else ""

    learned = sorted(observed)
    shown = learned[:MAX_PROMPT_CATEGORIES]
    if shown:
        learned_text = ", ".join(shown)
        if len(learned) > len(shown):
            learned_text += f" (plus {len(learned) - len(shown)} more already learned)"
    else:
        learned_text = "None yet — establish useful product-type categories from these images."

    return f"""You classify consecutive photos from a retail technology store photo shoot.
Each product was usually photographed from the front and then the back, but a
product may have one, two, or more photos. Use object appearance, packaging,
brand/model text, accessories visible in the package, and capture time. Never
assume strict pairs.

{listing}
{catalog_text}

Categories already established earlier in this same sorting operation:
{learned_text}

Return JSON only in this exact shape:
{{"items":[{{"filename":"exact filename","same_product_as_previous":false,
"category":"lowercase_english_snake_case_product_type",
"view":"front|back|side|detail|unknown","brand":"", "model":"",
"catalog_match":"", "confidence":0.0, "reason":"short reason"}}]}}

Category rules:
- Infer the product type from the image; the category list is NOT fixed.
- Reuse an established category EXACTLY when it already describes the product.
- If none of the established categories fits, CREATE a concise new category.
- A category describes product type, not brand, model, color, capacity, wattage,
  connector variant, marketing adjective, or other per-product feature unless it
  fundamentally changes the product type.
- Use short English lowercase snake_case names that are useful as folder names.
- Do not force a visible product into an unrelated existing category just to
  avoid creating a new one.
- Use "other" only when the product type genuinely cannot be inferred.

General rules:
- Include every image exactly once and preserve the listed order.
- For the first image, same_product_as_previous must be false.
- Confidence is from 0 to 1.
- Read visible package text carefully; do not invent a model number.
- catalog_match must be an exact catalog row or empty.
"""


def _write_registry(output: Path, observed: set[str]) -> None:
    path = output / CATEGORY_REGISTRY_NAME
    temp = output / f"{CATEGORY_REGISTRY_NAME}.tmp"
    payload = {
        "schema": 1,
        "mode": "ai_dynamic",
        "category_count": len(observed),
        "categories": sorted(observed),
    }
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def apply_dynamic_taxonomy(module: Any) -> None:
    """Patch the already-hardened engine with an AI-grown taxonomy registry."""

    observed: set[str] = set()
    module.DYNAMIC_CATEGORIES = observed

    base_cached_batches = module.cached_batches
    base_build_outputs = module.build_outputs

    def normalize_response(raw: str, photos: list[Any]) -> dict[str, Any]:
        return _normalize_response(module, observed, raw, photos)

    def prompt_for(photos: list[Any], catalog: str) -> str:
        return _prompt_for(photos, catalog, observed)

    def cached_batches(db: Any) -> list[dict[str, Any]]:
        responses = base_cached_batches(db)
        for response in responses:
            items = response.get("items", []) if isinstance(response, dict) else []
            if isinstance(items, list):
                valid_items = [item for item in items if isinstance(item, dict)]
                _register_items(module, observed, valid_items)
        return responses

    def build_outputs(
        items: list[dict[str, Any]], output: Path, confidence: float, dry_run: bool
    ) -> None:
        _register_items(module, observed, items)
        base_build_outputs(items, output, confidence, dry_run)
        if not dry_run:
            _write_registry(output, observed)

    module.normalize_response = normalize_response
    module.prompt_for = prompt_for
    module.cached_batches = cached_batches
    module.build_outputs = build_outputs
