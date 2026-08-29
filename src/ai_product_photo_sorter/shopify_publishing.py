"""Guarded Shopify Admin GraphQL staging and explicit publishing.

This layer sits after safe offline catalog exports. Preview is the default.
Remote writes require an explicit apply flag, create/update products as DRAFT,
and publishing requires a second explicit confirmation plus a publication ID.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

API_VERSION = "2026-07"
STATE_NAME = "shopify_publish_manifest.json"
AUDIT_NAME = "shopify_publish_audit.jsonl"
PREVIEW_NAME = "shopify_remote_preview.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _append_audit(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / AUDIT_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _normalize_domain(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value).rstrip("/")
    if "/" in value or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", value):
        raise ValueError("SHOPIFY_STORE_DOMAIN must look like store-name.myshopify.com")
    return value


def _credentials(store_domain: str | None = None, token: str | None = None) -> tuple[str, str]:
    domain = _normalize_domain(store_domain or os.getenv("SHOPIFY_STORE_DOMAIN", ""))
    access_token = (token or os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")).strip()
    if not access_token:
        raise ValueError("SHOPIFY_ADMIN_ACCESS_TOKEN is required for remote Shopify access")
    return domain, access_token


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"Required export file does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_export_package(export_manifest: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]], Path]:
    export_manifest = export_manifest.expanduser().resolve()
    if not export_manifest.is_file():
        raise ValueError(f"Catalog export manifest does not exist: {export_manifest}")
    try:
        payload = json.loads(export_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read catalog export manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != "catalog_export_profiles":
        raise ValueError("File is not a Product Sorter catalog export manifest")
    if bool(payload.get("publishing_enabled")) or int(payload.get("network_calls_performed", 0)) != 0:
        raise ValueError("Offline export manifest violates the expected no-publishing contract")
    outputs = payload.get("outputs", {})
    shopify_path = Path(str(outputs.get("shopify_draft_csv", "")))
    image_path = Path(str(outputs.get("image_upload_manifest", "")))
    if not shopify_path.is_absolute():
        shopify_path = export_manifest.parent / shopify_path
    if not image_path.is_absolute():
        image_path = export_manifest.parent / image_path
    products = _read_csv(shopify_path)
    images = _read_csv(image_path)
    if not products:
        raise ValueError("Shopify draft export contains no products")
    for row in products:
        if row.get("Status", "").strip().lower() != "draft":
            raise ValueError("Remote staging accepts Shopify rows only when Status=draft")
        if row.get("Published on online store", "").strip().lower() not in {"false", "0", "no"}:
            raise ValueError("Remote staging accepts only unpublished Shopify rows")
        if not row.get("Title", "").strip() or not row.get("SKU", "").strip() or not row.get("Price", "").strip():
            raise ValueError("Every Shopify staging row must have Title, SKU and Price")
    return payload, products, images, export_manifest


def _product_fingerprint(row: dict[str, str], image_rows: list[dict[str, str]]) -> str:
    stable = {
        "row": {key: row.get(key, "") for key in sorted(row)},
        "images": [
            {
                "position": item.get("position", ""),
                "filename": item.get("filename", ""),
                "local_relative_path": item.get("local_relative_path", ""),
            }
            for item in sorted(image_rows, key=lambda item: (item.get("position", ""), item.get("filename", "")))
        ],
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_plan(export_manifest: Path) -> dict[str, Any]:
    package, rows, image_rows, source = _load_export_package(export_manifest)
    images_by_sku: dict[str, list[dict[str, str]]] = {}
    for item in image_rows:
        images_by_sku.setdefault(item.get("sku", "").strip(), []).append(item)
    products = []
    for row in rows:
        sku = row["SKU"].strip()
        related = images_by_sku.get(sku, [])
        products.append(
            {
                "sku": sku,
                "title": row["Title"].strip(),
                "vendor": row.get("Vendor", "").strip(),
                "product_type": row.get("Type", "").strip(),
                "description_html": row.get("Description", "").strip(),
                "price": row["Price"].strip(),
                "barcode": row.get("Barcode", "").strip(),
                "fingerprint": _product_fingerprint(row, related),
                "images": related,
            }
        )
    return {
        "schema_version": 1,
        "mode": "shopify_publish_plan",
        "created_at": _now(),
        "api_version": API_VERSION,
        "source_export_manifest": str(source),
        "source_products": len(products),
        "default_remote_product_status": "DRAFT",
        "automatic_publishing_enabled": False,
        "inventory_writes_enabled": False,
        "products": products,
        "offline_export_summary": {
            "products": package.get("products"),
            "local_images_requiring_upload": package.get("local_images_requiring_upload"),
        },
    }


class ShopifyClient:
    def __init__(self, store_domain: str, access_token: str, *, api_version: str = API_VERSION, timeout: float = 45.0):
        self.store_domain = _normalize_domain(store_domain)
        self.access_token = access_token.strip()
        self.api_version = api_version
        self.timeout = timeout
        if not self.access_token:
            raise ValueError("Shopify access token cannot be blank")

    @property
    def endpoint(self) -> str:
        return f"https://{self.store_domain}/admin/api/{self.api_version}/graphql.json"

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.access_token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError(f"Shopify request failed: {exc}") from exc
        if payload.get("errors"):
            raise ValueError("Shopify GraphQL error: " + json.dumps(payload["errors"], ensure_ascii=False))
        return payload.get("data", {})

    def upload_staged_image(self, path: Path) -> str:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Image file does not exist: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        query = """
        mutation StagedUpload($input: [StagedUploadInput!]!) {
          stagedUploadsCreate(input: $input) {
            stagedTargets { url resourceUrl parameters { name value } }
            userErrors { field message }
          }
        }
        """
        data = self.graphql(query, {"input": [{"filename": path.name, "mimeType": mime, "httpMethod": "POST", "resource": "PRODUCT_IMAGE"}]})
        result = data.get("stagedUploadsCreate", {})
        _raise_user_errors(result, "stagedUploadsCreate")
        targets = result.get("stagedTargets") or []
        if len(targets) != 1:
            raise ValueError("Shopify did not return exactly one staged upload target")
        target = targets[0]
        boundary = "----ProductSorter" + uuid.uuid4().hex
        body = bytearray()
        for parameter in target.get("parameters", []):
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{parameter["name"]}"\r\n\r\n'.encode())
            body.extend(str(parameter["value"]).encode())
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode())
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            target["url"],
            data=bytes(body),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValueError(f"Shopify staged image upload failed for {path.name}: {exc}") from exc
        return str(target["resourceUrl"])


def _raise_user_errors(payload: dict[str, Any], operation: str) -> None:
    errors = payload.get("userErrors") or payload.get("mediaUserErrors") or []
    if errors:
        raise ValueError(f"Shopify {operation} error: " + json.dumps(errors, ensure_ascii=False))


def _sku_query(sku: str) -> str:
    escaped = sku.replace("\\", "\\\\").replace('"', '\\"')
    return f'sku:"{escaped}"'


def find_exact_sku(client: ShopifyClient, sku: str) -> list[dict[str, Any]]:
    query = """
    query VariantBySku($query: String!) {
      productVariants(first: 20, query: $query) {
        nodes {
          id sku barcode price
          inventoryItem { id sku }
          product { id title status handle vendor productType }
        }
      }
    }
    """
    data = client.graphql(query, {"query": _sku_query(sku)})
    nodes = data.get("productVariants", {}).get("nodes", [])
    return [item for item in nodes if str(item.get("sku") or item.get("inventoryItem", {}).get("sku") or "") == sku]


def remote_preview(export_manifest: Path, client: ShopifyClient, *, output_dir: Path | None = None) -> tuple[dict[str, Any], Path]:
    plan = build_plan(export_manifest)
    destination = (output_dir or Path(plan["source_export_manifest"]).parent / "shopify_remote").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for product in plan["products"]:
        matches = find_exact_sku(client, product["sku"])
        results.append(
            {
                "sku": product["sku"],
                "fingerprint": product["fingerprint"],
                "remote_matches": len(matches),
                "remote_product_ids": sorted({item.get("product", {}).get("id", "") for item in matches if item.get("product")}),
                "action": "create_draft" if not matches else ("managed_update_candidate" if len(matches) == 1 else "blocked_duplicate_sku"),
            }
        )
    preview = {
        "schema_version": 1,
        "mode": "shopify_remote_preview",
        "created_at": _now(),
        "store_domain": client.store_domain,
        "api_version": client.api_version,
        "network_writes_performed": 0,
        "products": results,
    }
    path = destination / PREVIEW_NAME
    _atomic_json(path, preview)
    return preview, path


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": 1,
            "mode": "shopify_publish_state",
            "revision": 0,
            "created_at": _now(),
            "updated_at": _now(),
            "automatic_publishing_enabled": False,
            "inventory_writes_enabled": False,
            "products": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read Shopify publish state: {exc}") from exc
    if payload.get("mode") != "shopify_publish_state":
        raise ValueError("File is not a Product Sorter Shopify publish state")
    return payload


def _product_input(product: dict[str, Any], *, product_id: str | None = None, status: str = "DRAFT") -> dict[str, Any]:
    payload = {
        "title": product["title"],
        "descriptionHtml": product["description_html"],
        "vendor": product["vendor"],
        "productType": product["product_type"],
        "status": status,
    }
    if product_id:
        payload["id"] = product_id
    return payload


def _variant_update(client: ShopifyClient, product_id: str, variant_id: str, product: dict[str, Any]) -> None:
    mutation = """
    mutation UpdateVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        product { id }
        productVariants { id price barcode inventoryItem { id sku } }
        userErrors { field message }
      }
    }
    """
    variant: dict[str, Any] = {
        "id": variant_id,
        "price": product["price"],
        "inventoryItem": {"sku": product["sku"]},
    }
    if product.get("barcode"):
        variant["barcode"] = product["barcode"]
    result = client.graphql(mutation, {"productId": product_id, "variants": [variant]}).get("productVariantsBulkUpdate", {})
    _raise_user_errors(result, "productVariantsBulkUpdate")


def _resolve_local_image(plan: dict[str, Any], image: dict[str, str]) -> Path | None:
    relative = image.get("local_relative_path", "").strip()
    if not relative:
        return None
    export_root = Path(plan["source_export_manifest"]).parent
    candidates = [export_root / relative, export_root.parent / relative]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def stage_drafts(
    export_manifest: Path,
    client: ShopifyClient,
    *,
    output_dir: Path | None = None,
    upload_images: bool = True,
) -> tuple[dict[str, Any], Path]:
    plan = build_plan(export_manifest)
    destination = (output_dir or Path(plan["source_export_manifest"]).parent / "shopify_remote").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    state_path = destination / STATE_NAME
    state = _load_state(state_path)
    state["store_domain"] = client.store_domain
    state["api_version"] = client.api_version
    state["source_export_manifest"] = plan["source_export_manifest"]

    for product in plan["products"]:
        sku = product["sku"]
        previous = state["products"].get(sku)
        matches = find_exact_sku(client, sku)
        if len(matches) > 1:
            raise ValueError(f"Blocked duplicate Shopify SKU: {sku} has {len(matches)} exact remote matches")
        if matches and (not previous or previous.get("product_id") != matches[0].get("product", {}).get("id")):
            raise ValueError(f"Blocked unmanaged existing Shopify SKU: {sku}")
        if previous and previous.get("fingerprint") == product["fingerprint"] and previous.get("stage_status") == "draft_staged":
            continue

        media: list[dict[str, str]] = []
        if not matches and upload_images:
            for image in product.get("images", []):
                local = _resolve_local_image(plan, image)
                if local is None:
                    continue
                resource_url = client.upload_staged_image(local)
                media.append({"originalSource": resource_url, "mediaContentType": "IMAGE", "alt": product["title"]})

        if matches:
            remote = matches[0]
            product_id = remote["product"]["id"]
            variant_id = remote["id"]
            mutation = """
            mutation UpdateDraft($product: ProductUpdateInput!) {
              productUpdate(product: $product) {
                product { id status }
                userErrors { field message }
              }
            }
            """
            result = client.graphql(mutation, {"product": _product_input(product, product_id=product_id, status="DRAFT")}).get("productUpdate", {})
            _raise_user_errors(result, "productUpdate")
            action = "update_managed_draft"
        else:
            mutation = """
            mutation CreateDraft($product: ProductCreateInput!, $media: [CreateMediaInput!]) {
              productCreate(product: $product, media: $media) {
                product { id status variants(first: 1) { nodes { id } } }
                userErrors { field message }
              }
            }
            """
            result = client.graphql(mutation, {"product": _product_input(product, status="DRAFT"), "media": media}).get("productCreate", {})
            _raise_user_errors(result, "productCreate")
            created = result.get("product") or {}
            variants = created.get("variants", {}).get("nodes", [])
            if not created.get("id") or len(variants) != 1:
                raise ValueError(f"Shopify productCreate returned incomplete IDs for {sku}")
            product_id = created["id"]
            variant_id = variants[0]["id"]
            action = "create_draft"

        _variant_update(client, product_id, variant_id, product)
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = _now()
        state["products"][sku] = {
            "sku": sku,
            "fingerprint": product["fingerprint"],
            "product_id": product_id,
            "variant_id": variant_id,
            "stage_status": "draft_staged",
            "published": False,
            "last_action": action,
            "updated_at": state["updated_at"],
        }
        _atomic_json(state_path, state)
        _append_audit(
            state_path,
            {
                "revision": state["revision"],
                "timestamp": state["updated_at"],
                "action": action,
                "sku": sku,
                "product_id": product_id,
                "variant_id": variant_id,
                "remote_status": "DRAFT",
                "inventory_written": False,
                "automatic": False,
            },
        )
    return state, state_path


def publish_staged(
    state_path: Path,
    client: ShopifyClient,
    *,
    publication_id: str,
    confirmation: str,
) -> tuple[dict[str, Any], Path]:
    if confirmation != "PUBLISH":
        raise ValueError("Explicit publish requires confirmation text exactly equal to PUBLISH")
    if not publication_id.startswith("gid://shopify/Publication/"):
        raise ValueError("A valid Shopify publication GID is required")
    state_path = state_path.expanduser().resolve()
    state = _load_state(state_path)
    if state.get("store_domain") != client.store_domain:
        raise ValueError("Shopify state belongs to a different store domain")
    for sku, item in state.get("products", {}).items():
        if item.get("stage_status") != "draft_staged":
            raise ValueError(f"Product {sku} is not safely staged as draft")
        if item.get("published"):
            continue
        update = """
        mutation Activate($product: ProductUpdateInput!) {
          productUpdate(product: $product) { product { id status } userErrors { field message } }
        }
        """
        result = client.graphql(update, {"product": {"id": item["product_id"], "status": "ACTIVE"}}).get("productUpdate", {})
        _raise_user_errors(result, "productUpdate status ACTIVE")
        publish = """
        mutation Publish($id: ID!, $input: [PublicationInput!]!) {
          publishablePublish(id: $id, input: $input) {
            publishable { publishedOnPublication(publicationId: $publicationId) }
            userErrors { field message }
          }
        }
        """
        # publishedOnPublication needs a literal field argument, so query a portable payload instead.
        publish = """
        mutation Publish($id: ID!, $input: [PublicationInput!]!) {
          publishablePublish(id: $id, input: $input) {
            publishable { availablePublicationsCount { count } resourcePublicationsCount { count } }
            userErrors { field message }
          }
        }
        """
        result = client.graphql(publish, {"id": item["product_id"], "input": [{"publicationId": publication_id}]}).get("publishablePublish", {})
        _raise_user_errors(result, "publishablePublish")
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = _now()
        item["published"] = True
        item["stage_status"] = "published"
        item["publication_id"] = publication_id
        item["published_at"] = state["updated_at"]
        _atomic_json(state_path, state)
        _append_audit(
            state_path,
            {
                "revision": state["revision"],
                "timestamp": state["updated_at"],
                "action": "publish_explicit",
                "sku": sku,
                "product_id": item["product_id"],
                "publication_id": publication_id,
                "automatic": False,
            },
        )
    return state, state_path


def rollback_publication(
    state_path: Path,
    client: ShopifyClient,
    *,
    confirmation: str,
) -> tuple[dict[str, Any], Path]:
    if confirmation != "UNPUBLISH":
        raise ValueError("Rollback requires confirmation text exactly equal to UNPUBLISH")
    state_path = state_path.expanduser().resolve()
    state = _load_state(state_path)
    if state.get("store_domain") != client.store_domain:
        raise ValueError("Shopify state belongs to a different store domain")
    mutation = """
    mutation Unpublish($id: ID!, $input: [PublicationInput!]!) {
      publishableUnpublish(id: $id, input: $input) {
        publishable { availablePublicationsCount { count } resourcePublicationsCount { count } }
        userErrors { field message }
      }
    }
    """
    set_draft = """
    mutation Draft($product: ProductUpdateInput!) {
      productUpdate(product: $product) { product { id status } userErrors { field message } }
    }
    """
    for sku, item in state.get("products", {}).items():
        if not item.get("published"):
            continue
        publication_id = str(item.get("publication_id", ""))
        if publication_id:
            result = client.graphql(mutation, {"id": item["product_id"], "input": [{"publicationId": publication_id}]}).get("publishableUnpublish", {})
            _raise_user_errors(result, "publishableUnpublish")
        result = client.graphql(set_draft, {"product": {"id": item["product_id"], "status": "DRAFT"}}).get("productUpdate", {})
        _raise_user_errors(result, "productUpdate status DRAFT")
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = _now()
        item["published"] = False
        item["stage_status"] = "draft_staged"
        _atomic_json(state_path, state)
        _append_audit(state_path, {"revision": state["revision"], "timestamp": state["updated_at"], "action": "unpublish_rollback", "sku": sku, "product_id": item["product_id"], "automatic": False})
    return state, state_path


def apply_shopify_publishing(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--shopify-preview", type=Path)
        parser.add_argument("--shopify-stage", type=Path)
        parser.add_argument("--shopify-publish", type=Path)
        parser.add_argument("--shopify-rollback", type=Path)
        parser.add_argument("--shopify-output", type=Path)
        parser.add_argument("--shopify-store")
        parser.add_argument("--shopify-token")
        parser.add_argument("--shopify-api-version", default=os.getenv("SHOPIFY_API_VERSION", API_VERSION))
        parser.add_argument("--shopify-publication-id", default=os.getenv("SHOPIFY_PUBLICATION_ID", ""))
        parser.add_argument("--shopify-confirm", default="")
        parser.add_argument("--shopify-no-images", action="store_true")
        known, remaining = parser.parse_known_args(original[1:])
        action_count = sum(value is not None for value in (known.shopify_preview, known.shopify_stage, known.shopify_publish, known.shopify_rollback))
        try:
            if action_count > 1:
                raise SystemExit("Choose exactly one Shopify action")
            if action_count == 1:
                domain, token = _credentials(known.shopify_store, known.shopify_token)
                client = ShopifyClient(domain, token, api_version=known.shopify_api_version)
                if known.shopify_preview is not None:
                    preview, path = remote_preview(known.shopify_preview, client, output_dir=known.shopify_output)
                    print(f"Shopify remote preview: {path}")
                    print(f"Products: {len(preview['products'])} · remote writes: 0")
                elif known.shopify_stage is not None:
                    state, path = stage_drafts(known.shopify_stage, client, output_dir=known.shopify_output, upload_images=not known.shopify_no_images)
                    print(f"Shopify draft state: {path}")
                    print(f"Managed products: {len(state['products'])} · publication writes: 0")
                elif known.shopify_publish is not None:
                    state, path = publish_staged(known.shopify_publish, client, publication_id=known.shopify_publication_id, confirmation=known.shopify_confirm)
                    print(f"Shopify publish state: {path}")
                    print(f"Published products: {sum(bool(item.get('published')) for item in state['products'].values())}")
                else:
                    state, path = rollback_publication(known.shopify_rollback, client, confirmation=known.shopify_confirm)
                    print(f"Shopify rollback state: {path}")
                    print(f"Published products remaining: {sum(bool(item.get('published')) for item in state['products'].values())}")
                raise SystemExit(0)
            sys.argv = [original[0], *remaining]
            return base_parse_args(env_file)
        except (ValueError, OSError) as exc:
            raise SystemExit(str(exc)) from exc
        finally:
            sys.argv = original

    module.parse_args = parse_args
