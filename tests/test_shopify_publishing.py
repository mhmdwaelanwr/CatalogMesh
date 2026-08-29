from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter.shopify_environment import prepare_shopify_environment_fields
from ai_product_photo_sorter.shopify_publishing import (
    build_plan,
    publish_staged,
    remote_preview,
    rollback_publication,
    stage_drafts,
)
from ai_product_photo_sorter.shopify_safety import apply_shopify_safety


class FakeShopifyClient:
    def __init__(self, *, existing=None):
        self.store_domain = "mock-store.myshopify.com"
        self.api_version = "2026-07"
        self.existing = list(existing or [])
        self.calls: list[tuple[str, dict]] = []
        self.uploads: list[str] = []

    def upload_staged_image(self, path: Path) -> str:
        self.uploads.append(path.name)
        return f"https://staged.example/{path.name}"

    def graphql(self, query: str, variables: dict | None = None):
        variables = variables or {}
        self.calls.append((query, variables))
        if "VariantBySku" in query:
            return {"productVariants": {"nodes": self.existing}}
        if "CreateDraft" in query:
            return {
                "productCreate": {
                    "product": {
                        "id": "gid://shopify/Product/100",
                        "status": "DRAFT",
                        "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/200"}]},
                    },
                    "userErrors": [],
                }
            }
        if "UpdateDraft" in query:
            return {"productUpdate": {"product": {"id": variables["product"]["id"], "status": "DRAFT"}, "userErrors": []}}
        if "UpdateVariant" in query:
            return {
                "productVariantsBulkUpdate": {
                    "product": {"id": variables["productId"]},
                    "productVariants": [{"id": variables["variants"][0]["id"]}],
                    "userErrors": [],
                }
            }
        if "Activate" in query:
            return {"productUpdate": {"product": {"id": variables["product"]["id"], "status": "ACTIVE"}, "userErrors": []}}
        if "Publish(" in query:
            return {"publishablePublish": {"publishable": {}, "userErrors": []}}
        if "Unpublish(" in query:
            return {"publishableUnpublish": {"publishable": {}, "userErrors": []}}
        if "mutation Draft(" in query:
            return {"productUpdate": {"product": {"id": variables["product"]["id"], "status": "DRAFT"}, "userErrors": []}}
        raise AssertionError(query)


class ShopifyPublishingTests(unittest.TestCase):
    def make_export(self, root: Path, *, with_image: bool = True) -> Path:
        exports = root / "exports"
        exports.mkdir(parents=True)
        shopify = exports / "shopify_products_draft.csv"
        with shopify.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "Title", "URL handle", "Description", "Vendor", "Type",
                    "Published on online store", "Status", "SKU", "Barcode", "Price",
                    "Option1 name", "Option1 value",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Title": "Mock Mouse",
                    "URL handle": "mock-mouse",
                    "Description": "Mock description",
                    "Vendor": "MockLab",
                    "Type": "mouse",
                    "Published on online store": "false",
                    "Status": "draft",
                    "SKU": "SKU-M100",
                    "Barcode": "6221111000017",
                    "Price": "399",
                    "Option1 name": "Default Title",
                    "Option1 value": "Default Title",
                }
            )
        image_manifest = exports / "image_upload_manifest.csv"
        with image_manifest.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["group_id", "sku", "position", "view", "filename", "local_relative_path", "public_image_url", "status"],
            )
            writer.writeheader()
            if with_image:
                photo = root / "Product_0001" / "front.jpg"
                photo.parent.mkdir(parents=True)
                photo.write_bytes(b"mock-jpeg")
                writer.writerow(
                    {
                        "group_id": "Product_0001",
                        "sku": "SKU-M100",
                        "position": "1",
                        "view": "front",
                        "filename": "front.jpg",
                        "local_relative_path": "Product_0001/front.jpg",
                        "public_image_url": "",
                        "status": "requires_upload",
                    }
                )
        manifest = exports / "catalog_export_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "catalog_export_profiles",
                    "products": 1,
                    "local_images_requiring_upload": 1 if with_image else 0,
                    "publishing_enabled": False,
                    "network_calls_performed": 0,
                    "outputs": {
                        "shopify_draft_csv": str(shopify),
                        "image_upload_manifest": str(image_manifest),
                    },
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_build_plan_is_draft_and_inventory_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(self.make_export(Path(tmp)))
            self.assertEqual(plan["source_products"], 1)
            self.assertEqual(plan["default_remote_product_status"], "DRAFT")
            self.assertFalse(plan["automatic_publishing_enabled"])
            self.assertFalse(plan["inventory_writes_enabled"])
            self.assertEqual(plan["products"][0]["sku"], "SKU-M100")

    def test_remote_preview_performs_queries_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeShopifyClient()
            preview, path = remote_preview(self.make_export(root), client)
            self.assertTrue(path.is_file())
            self.assertEqual(preview["network_writes_performed"], 0)
            self.assertEqual(preview["products"][0]["action"], "create_draft")
            self.assertEqual(len(client.calls), 1)
            self.assertIn("VariantBySku", client.calls[0][0])

    def test_stage_creates_draft_updates_variant_and_uploads_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeShopifyClient()
            state, path = stage_drafts(self.make_export(root), client)
            item = state["products"]["SKU-M100"]
            self.assertEqual(item["stage_status"], "draft_staged")
            self.assertFalse(item["published"])
            self.assertEqual(client.uploads, ["front.jpg"])
            create = next(variables for query, variables in client.calls if "CreateDraft" in query)
            self.assertEqual(create["product"]["status"], "DRAFT")
            self.assertEqual(len(create["media"]), 1)
            variant = next(variables for query, variables in client.calls if "UpdateVariant" in query)
            self.assertEqual(variant["variants"][0]["inventoryItem"]["sku"], "SKU-M100")
            self.assertNotIn("inventoryQuantities", variant["variants"][0])
            self.assertTrue((path.parent / "shopify_publish_audit.jsonl").is_file())

    def test_stage_blocks_unmanaged_existing_sku(self):
        existing = [
            {
                "id": "gid://shopify/ProductVariant/999",
                "sku": "SKU-M100",
                "product": {"id": "gid://shopify/Product/999", "status": "ACTIVE"},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unmanaged existing Shopify SKU"):
                stage_drafts(self.make_export(Path(tmp), with_image=False), FakeShopifyClient(existing=existing))

    def test_publish_requires_exact_confirmation_and_can_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeShopifyClient()
            _, state_path = stage_drafts(self.make_export(root, with_image=False), client)
            with self.assertRaisesRegex(ValueError, "PUBLISH"):
                publish_staged(
                    state_path,
                    client,
                    publication_id="gid://shopify/Publication/123",
                    confirmation="yes",
                )
            state, _ = publish_staged(
                state_path,
                client,
                publication_id="gid://shopify/Publication/123",
                confirmation="PUBLISH",
            )
            self.assertTrue(state["products"]["SKU-M100"]["published"])
            with self.assertRaisesRegex(ValueError, "UNPUBLISH"):
                rollback_publication(state_path, client, confirmation="no")
            state, _ = rollback_publication(state_path, client, confirmation="UNPUBLISH")
            self.assertFalse(state["products"]["SKU-M100"]["published"])
            self.assertEqual(state["products"]["SKU-M100"]["stage_status"], "draft_staged")

    def test_cli_guard_requires_apply_and_blocks_token_argument(self):
        called = []
        module = SimpleNamespace(parse_args=lambda env: called.append(list(sys.argv)) or "ok")
        apply_shopify_safety(module)
        with patch.object(sys, "argv", ["product-sorter", "--shopify-stage", "export.json"]):
            with self.assertRaisesRegex(SystemExit, "--shopify-apply"):
                module.parse_args(Path(".env"))
        with patch.object(sys, "argv", ["product-sorter", "--shopify-stage", "export.json", "--shopify-apply"]):
            self.assertEqual(module.parse_args(Path(".env")), "ok")
        self.assertNotIn("--shopify-apply", called[-1])
        with patch.object(sys, "argv", ["product-sorter", "--shopify-preview", "export.json", "--shopify-token", "secret"]):
            with self.assertRaisesRegex(SystemExit, "Do not pass Shopify tokens"):
                module.parse_args(Path(".env"))

    def test_shopify_environment_validation(self):
        env = SimpleNamespace(_ENV_FIELDS=(), _validate_setting=lambda name, value: value)
        prepare_shopify_environment_fields(env)
        self.assertIn("SHOPIFY_STORE_DOMAIN", env._ENV_FIELDS)
        self.assertEqual(env._validate_setting("SHOPIFY_STORE_DOMAIN", "https://demo.myshopify.com/"), "demo.myshopify.com")
        self.assertEqual(env._validate_setting("SHOPIFY_API_VERSION", "2026-07"), "2026-07")
        self.assertEqual(env._validate_setting("SHOPIFY_PUBLICATION_ID", "gid://shopify/Publication/123"), "gid://shopify/Publication/123")
        with self.assertRaises(ValueError):
            env._validate_setting("SHOPIFY_STORE_DOMAIN", "example.com")


if __name__ == "__main__":
    unittest.main()
