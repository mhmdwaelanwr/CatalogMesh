"""Safe offline catalog export profiles built from human-confirmed SKU matches.

Export generation is deliberately file-only. It never calls Shopify/PIM/ERP APIs,
never changes the source catalog, and never invents inventory or image URLs.
Shopify output is draft + unpublished and local photos are emitted separately in
an upload manifest until a public URL is supplied by a later publishing stage.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPORT_MANIFEST = "catalog_export_manifest.json"
SHOPIFY_CSV = "shopify_products_draft.csv"
PIM_CSV = "catalog_confirmed_products.csv"
IMAGE_MANIFEST = "image_upload_manifest.csv"
VALIDATION_CSV = "export_validation_issues.csv"

SHOPIFY_FIELDS = [
    "Title",
    "URL handle",
    "Description",
    "Vendor",
    "Type",
    "Published on online store",
    "Status",
    "SKU",
    "Barcode",
    "Price",
    "Option1 name",
    "Option1 value",
]

_FIELD_ALIASES = {
    "sku": ("sku", "sku_id", "stock_code", "stockcode", "item_code", "itemcode", "product_code", "productcode", "code"),
    "barcode": ("barcode", "bar_code", "ean", "ean13", "ean_13", "upc", "upca", "upc_a", "gtin", "gtin13", "gtin_13"),
    "title": ("title", "product_name", "productname", "name", "product"),
    "description": ("description", "body", "details"),
    "vendor": ("vendor", "brand", "manufacturer", "maker"),
    "price": ("price", "selling_price", "sale_price", "retail_price", "unit_price"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"[^\w]+", "_", text, flags=re.UNICODE).strip("_")


def _field(fields: dict[str, Any], logical: str) -> str:
    normalized = {_header(key): str(value).strip() for key, value in fields.items() if str(value).strip()}
    for alias in _FIELD_ALIASES[logical]:
        if alias in normalized:
            return normalized[alias]
    return ""


def _slug(value: str, fallback: str) -> str:
    source = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    source = re.sub(r"[^a-z0-9]+", "-", source).strip("-")
    if not source:
        source = re.sub(r"[^a-z0-9]+", "-", fallback.casefold()).strip("-") or "product"
    return source[:255]


def _candidate(group: dict[str, Any]) -> dict[str, Any]:
    decision = group.get("decision", {})
    if str(decision.get("status", "")) != "confirmed":
        raise ValueError(f"Group is not human-confirmed: {group.get('group_id', '')}")
    candidate = decision.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("row_id"):
        raise ValueError(f"Confirmed group is missing its catalog candidate snapshot: {group.get('group_id', '')}")
    return candidate


def _load_match_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"SKU match manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read SKU match manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != "sku_candidate_matching":
        raise ValueError("File is not a Product Sorter SKU match manifest")
    summary = payload.get("summary", {})
    groups = payload.get("groups", [])
    if not isinstance(groups, list) or not groups:
        raise ValueError("SKU match manifest contains no product groups")
    pending = [
        group.get("group_id", "")
        for group in groups
        if str(group.get("decision", {}).get("status", "")) != "confirmed"
    ]
    if pending or not bool(summary.get("catalog_ready_for_export")):
        preview = ", ".join(str(value) for value in pending[:5])
        raise ValueError(
            "Catalog export is fail-closed until every approved group is human-confirmed"
            + (f": {preview}" if preview else "")
        )
    if bool(summary.get("publishing_enabled")):
        raise ValueError("Unexpected publishing-enabled SKU manifest; offline exporter refuses it")
    return payload, path


def _approved_metadata(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = str(manifest.get("approved_groups_source", "")).strip()
    if not source:
        return {}
    path = Path(source)
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        group_id = str(row.get("group_id", "")).strip()
        if not group_id:
            continue
        result[group_id] = {
            "filenames": [
                value.strip()
                for value in str(row.get("filenames", "")).split("|")
                if value.strip()
            ],
            "views": [
                value.strip()
                for value in str(row.get("views", "")).split("|")
                if value.strip()
            ],
        }
    return result


def _unique_handles(rows: list[dict[str, Any]]) -> None:
    used: dict[str, int] = {}
    for row in rows:
        base = str(row["URL handle"])
        used[base] = used.get(base, 0) + 1
        if used[base] > 1:
            row["URL handle"] = f"{base}-{used[base]}"


def _resolve_product(group: dict[str, Any]) -> dict[str, Any]:
    candidate = _candidate(group)
    fields = candidate.get("fields", {}) if isinstance(candidate.get("fields"), dict) else {}
    sku = _field(fields, "sku")
    barcode = _field(fields, "barcode")
    title = _field(fields, "title")
    description = _field(fields, "description")
    vendor = _field(fields, "vendor") or str(group.get("brand", "")).strip()
    if not title:
        title = " ".join(
            value
            for value in (
                str(group.get("brand", "")).strip(),
                str(group.get("model", "")).strip(),
            )
            if value
        )
    if not title:
        title = str(group.get("group_id", "")).replace("_", " ").strip()
    return {
        "group_id": str(group.get("group_id", "")),
        "category": str(group.get("category", "")).strip(),
        "brand": str(group.get("brand", "")).strip(),
        "model": str(group.get("model", "")).strip(),
        "filenames": list(group.get("filenames", [])),
        "row_id": str(candidate.get("row_id", "")),
        "ranking_score": candidate.get("ranking_score", ""),
        "tier": str(candidate.get("tier", "")),
        "title": title,
        "description": description,
        "vendor": vendor,
        "sku": sku,
        "barcode": barcode,
        "price": _field(fields, "price"),
        "catalog_fields": fields,
    }


def _shopify_price_is_safe(value: str) -> bool:
    value = value.strip()
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", value))


def _validation(products: list[dict[str, Any]], *, profile: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    seen_sku: dict[str, str] = {}
    shopify_requested = profile in {"all", "shopify"}
    for product in products:
        group_id = product["group_id"]
        if not product["title"]:
            issues.append({
                "severity": "error",
                "group_id": group_id,
                "field": "title",
                "message": "No safe product title could be resolved",
            })
        if not product["sku"]:
            issues.append({
                "severity": "warning",
                "group_id": group_id,
                "field": "sku",
                "message": "Confirmed catalog row has no recognized SKU field",
            })
        elif product["sku"] in seen_sku and seen_sku[product["sku"]] != group_id:
            issues.append({
                "severity": "warning",
                "group_id": group_id,
                "field": "sku",
                "message": f"SKU is shared with {seen_sku[product['sku']]}",
            })
        else:
            seen_sku[product["sku"]] = group_id
        if not product["barcode"]:
            issues.append({
                "severity": "info",
                "group_id": group_id,
                "field": "barcode",
                "message": "No recognized barcode field in confirmed catalog row",
            })
        if not product["price"]:
            issues.append({
                "severity": "error" if shopify_requested else "info",
                "group_id": group_id,
                "field": "price",
                "message": (
                    "Shopify export is blocked because a blank imported price can default to 0.00"
                    if shopify_requested
                    else "No recognized price field in confirmed catalog row"
                ),
            })
        elif shopify_requested and not _shopify_price_is_safe(str(product["price"])):
            issues.append({
                "severity": "error",
                "group_id": group_id,
                "field": "price",
                "message": "Shopify price must contain only a numeric monetary value without a currency symbol",
            })
        if product["filenames"]:
            issues.append({
                "severity": "info",
                "group_id": group_id,
                "field": "images",
                "message": "Local photos are not public URLs; emitted separately in image upload manifest",
            })
    return issues


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _shopify_rows(products: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for product in products:
        rows.append({
            "Title": product["title"],
            "URL handle": _slug(product["title"], product["group_id"]),
            "Description": product["description"],
            "Vendor": product["vendor"],
            "Type": product["category"],
            "Published on online store": "false",
            "Status": "draft",
            "SKU": product["sku"],
            "Barcode": product["barcode"],
            "Price": product["price"],
            "Option1 name": "Default Title",
            "Option1 value": "Default Title",
        })
    _unique_handles(rows)
    return rows


def _pim_rows(products: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for product in products:
        result.append({
            "group_id": product["group_id"],
            "category": product["category"],
            "brand": product["brand"],
            "model": product["model"],
            "catalog_row_id": product["row_id"],
            "ranking_score": str(product["ranking_score"]),
            "evidence_tier": product["tier"],
            "sku": product["sku"],
            "barcode": product["barcode"],
            "title": product["title"],
            "description": product["description"],
            "vendor": product["vendor"],
            "price": product["price"],
            "local_image_filenames": " | ".join(product["filenames"]),
            "catalog_fields_json": json.dumps(
                product["catalog_fields"], ensure_ascii=False, sort_keys=True
            ),
        })
    return result


def _image_rows(
    products: list[dict[str, Any]],
    approved: dict[str, dict[str, Any]],
    review_root: Path | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    for product in products:
        group_id = product["group_id"]
        metadata = approved.get(group_id, {})
        filenames = list(metadata.get("filenames") or product["filenames"])
        views = list(metadata.get("views") or [])
        for index, filename in enumerate(filenames, 1):
            local_relative = ""
            if review_root and review_root.is_dir():
                matches = [path for path in review_root.rglob(filename) if path.is_file()]
                if len(matches) == 1:
                    local_relative = matches[0].relative_to(review_root).as_posix()
                elif len(matches) > 1:
                    issues.append({
                        "severity": "warning",
                        "group_id": group_id,
                        "field": "images",
                        "message": f"Filename is not unique under review output: {filename}",
                    })
            rows.append({
                "group_id": group_id,
                "sku": product["sku"],
                "position": str(index),
                "view": views[index - 1] if index <= len(views) else "",
                "filename": filename,
                "local_relative_path": local_relative,
                "public_image_url": "",
                "status": "requires_upload",
            })
    return rows, issues


def _remove_stale_requested_outputs(destination: Path, profile: str) -> None:
    names = {IMAGE_MANIFEST, EXPORT_MANIFEST}
    if profile in {"all", "shopify"}:
        names.add(SHOPIFY_CSV)
    if profile in {"all", "pim"}:
        names.add(PIM_CSV)
    for name in names:
        try:
            (destination / name).unlink(missing_ok=True)
        except OSError:
            pass


def generate_exports(
    match_manifest: Path,
    *,
    output_dir: Path | None = None,
    profile: str = "all",
) -> tuple[dict[str, Any], Path]:
    profile = profile.strip().lower()
    if profile not in {"all", "shopify", "pim"}:
        raise ValueError("Export profile must be one of: all, shopify, pim")
    source, source_path = _load_match_manifest(match_manifest)
    products = [_resolve_product(group) for group in source["groups"]]
    approved = _approved_metadata(source)
    approved_source = str(source.get("approved_groups_source", "")).strip()
    review_root = Path(approved_source).parent if approved_source else None

    destination = (output_dir or source_path.parent / "exports").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    issues = _validation(products, profile=profile)
    image_rows, image_issues = _image_rows(products, approved, review_root)
    issues.extend(image_issues)

    validation_path = destination / VALIDATION_CSV
    _write_csv(validation_path, ["severity", "group_id", "field", "message"], issues)
    if any(issue["severity"] == "error" for issue in issues):
        _remove_stale_requested_outputs(destination, profile)
        raise ValueError(
            f"Export validation found blocking errors; review {validation_path}. "
            "No requested import-ready file was written."
        )

    outputs: dict[str, str] = {}
    if profile in {"all", "shopify"}:
        path = destination / SHOPIFY_CSV
        _write_csv(path, SHOPIFY_FIELDS, _shopify_rows(products))
        outputs["shopify_draft_csv"] = str(path)
    if profile in {"all", "pim"}:
        path = destination / PIM_CSV
        fields = [
            "group_id", "category", "brand", "model", "catalog_row_id", "ranking_score",
            "evidence_tier", "sku", "barcode", "title", "description", "vendor", "price",
            "local_image_filenames", "catalog_fields_json",
        ]
        _write_csv(path, fields, _pim_rows(products))
        outputs["neutral_pim_csv"] = str(path)

    image_path = destination / IMAGE_MANIFEST
    _write_csv(
        image_path,
        [
            "group_id", "sku", "position", "view", "filename",
            "local_relative_path", "public_image_url", "status",
        ],
        image_rows,
    )
    outputs["image_upload_manifest"] = str(image_path)
    outputs["validation_issues"] = str(validation_path)

    summary = {
        "schema_version": 1,
        "mode": "catalog_export_profiles",
        "profile": profile,
        "created_at": _now(),
        "source_match_manifest": str(source_path),
        "products": len(products),
        "confirmed_groups": len(products),
        "pending_groups": 0,
        "shopify_status": "draft" if profile in {"all", "shopify"} else "not_generated",
        "shopify_published_on_online_store": False,
        "public_image_urls_invented": 0,
        "local_images_requiring_upload": len(image_rows),
        "validation_issues": len(issues),
        "blocking_errors": 0,
        "publishing_enabled": False,
        "network_calls_performed": 0,
        "source_files_modified": False,
        "outputs": outputs,
    }
    manifest_path = destination / EXPORT_MANIFEST
    temp = manifest_path.with_name(manifest_path.name + ".tmp")
    temp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, manifest_path)
    return summary, manifest_path


def apply_catalog_exports(module: Any) -> None:
    """Add standalone safe export actions without entering the AI inference path."""

    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--export-catalog", type=Path)
        parser.add_argument("--export-output", type=Path)
        parser.add_argument(
            "--export-profile",
            choices=("all", "shopify", "pim"),
            default="all",
        )
        known, remaining = parser.parse_known_args(original[1:])
        try:
            if known.export_catalog is not None:
                summary, path = generate_exports(
                    known.export_catalog,
                    output_dir=known.export_output,
                    profile=known.export_profile,
                )
                print(f"Catalog export manifest: {path}")
                for name, output in summary["outputs"].items():
                    print(f"{name}: {output}")
                print(
                    f"Products: {summary['products']} · Shopify status: {summary['shopify_status']} · "
                    f"local images requiring upload: {summary['local_images_requiring_upload']}"
                )
                print(
                    "Offline export only: publishing is disabled and no network calls were performed."
                )
                raise SystemExit(0)
            if "--export-output" in original or "--export-profile" in original:
                raise SystemExit("Export options require --export-catalog")
            sys.argv = [original[0], *remaining]
            return base_parse_args(env_file)
        except (ValueError, OSError) as exc:
            raise SystemExit(str(exc)) from exc
        finally:
            sys.argv = original

    module.parse_args = parse_args
