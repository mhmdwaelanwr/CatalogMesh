from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.shopify_publishing import build_plan
from ai_product_photo_sorter.shopify_safety import install_shopify_export_guards


install_shopify_export_guards()


class ShopifyDuplicateGuardTests(unittest.TestCase):
    def test_duplicate_sku_is_blocked_before_plan_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shopify = root / "shopify_products_draft.csv"
            fields = [
                "Title", "URL handle", "Description", "Vendor", "Type",
                "Published on online store", "Status", "SKU", "Barcode", "Price",
                "Option1 name", "Option1 value",
            ]
            with shopify.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for title in ("First K200", "Second K200"):
                    writer.writerow(
                        {
                            "Title": title,
                            "URL handle": title.lower().replace(" ", "-"),
                            "Description": "",
                            "Vendor": "MockLab",
                            "Type": "keyboard",
                            "Published on online store": "false",
                            "Status": "draft",
                            "SKU": "SKU-K200",
                            "Barcode": "6221111000031",
                            "Price": "599",
                            "Option1 name": "Default Title",
                            "Option1 value": "Default Title",
                        }
                    )
            images = root / "image_upload_manifest.csv"
            with images.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["group_id", "sku", "position", "view", "filename", "local_relative_path", "public_image_url", "status"],
                )
                writer.writeheader()
            manifest = root / "catalog_export_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "mode": "catalog_export_profiles",
                        "publishing_enabled": False,
                        "network_calls_performed": 0,
                        "outputs": {
                            "shopify_draft_csv": str(shopify),
                            "image_upload_manifest": str(images),
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate SKU"):
                build_plan(manifest)


if __name__ == "__main__":
    unittest.main()
