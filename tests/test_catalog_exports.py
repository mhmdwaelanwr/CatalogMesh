from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.catalog_exports import (
    EXPORT_MANIFEST,
    IMAGE_MANIFEST,
    PIM_CSV,
    SHOPIFY_CSV,
    VALIDATION_CSV,
    generate_exports,
)


ROOT = Path(__file__).resolve().parent.parent


class CatalogExportTests(unittest.TestCase):
    def _approved(self, root: Path) -> Path:
        path = root / "approved_product_groups.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "group_id", "category", "brand", "model", "photo_count",
                    "filenames", "views", "notes",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "group_id": "Product_0001_MockLab_M100",
                    "category": "mouse",
                    "brand": "MockLab",
                    "model": "M100",
                    "photo_count": "2",
                    "filenames": "A_front.jpg | A_back.jpg",
                    "views": "front | back",
                    "notes": "approved",
                }
            )
            writer.writerow(
                {
                    "group_id": "Product_0002_MockLab_M100",
                    "category": "mouse",
                    "brand": "MockLab",
                    "model": "M100",
                    "photo_count": "1",
                    "filenames": "B_front.jpg",
                    "views": "front",
                    "notes": "approved",
                }
            )
        for filename in ("A_front.jpg", "A_back.jpg", "B_front.jpg"):
            photo = root / "mouse" / filename
            photo.parent.mkdir(parents=True, exist_ok=True)
            photo.write_bytes(b"mock-jpeg-bytes")
        return path

    def _manifest(
        self,
        root: Path,
        *,
        confirmed: bool = True,
        first_price: str = "399.00",
        second_price: str = "429",
    ) -> Path:
        approved = self._approved(root)

        def group(group_id: str, filename: str, sku: str, barcode: str, price: str):
            candidate = {
                "rank": 1,
                "row_id": f"Catalog!{sku}",
                "ranking_score": 1.0,
                "tier": "exact_barcode",
                "reasons": ["exact barcode"],
                "display": f"{sku} MockLab M100",
                "fields": {
                    "SKU": sku,
                    "Barcode": barcode,
                    "Brand": "MockLab",
                    "Model": "M100",
                    "Category": "mouse",
                    "Name": "MockLab M100 Mouse",
                    "Description": "Confirmed catalog description",
                    "Price": price,
                },
            }
            decision = (
                {
                    "status": "confirmed",
                    "row_id": candidate["row_id"],
                    "confirmed_at": "2026-08-29T00:00:00+00:00",
                    "candidate": candidate,
                }
                if confirmed
                else {"status": "pending", "row_id": "", "confirmed_at": ""}
            )
            return {
                "group_id": group_id,
                "category": "mouse",
                "brand": "MockLab",
                "model": "M100",
                "filenames": [filename],
                "notes": "approved",
                "candidates": [candidate],
                "decision": decision,
            }

        groups = [
            group(
                "Product_0001_MockLab_M100",
                "A_front.jpg",
                "ML-M100-A",
                "6221111000017",
                first_price,
            ),
            group(
                "Product_0002_MockLab_M100",
                "B_front.jpg",
                "ML-M100-B",
                "6221111000024",
                second_price,
            ),
        ]
        payload = {
            "schema_version": 1,
            "mode": "sku_candidate_matching",
            "revision": 2 if confirmed else 0,
            "approved_groups_source": str(approved.resolve()),
            "catalog_source": str((root / "catalog.xlsx").resolve()),
            "groups": groups,
            "summary": {
                "groups": 2,
                "confirmed_groups": 2 if confirmed else 0,
                "pending_groups": 0 if confirmed else 2,
                "catalog_ready_for_export": confirmed,
                "automatic_matching_enabled": False,
                "human_confirmation_required": True,
                "publishing_enabled": False,
            },
        }
        path = root / "sku_match_manifest.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_export_is_fail_closed_until_every_group_is_human_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root, confirmed=False)
            output = root / "exports"
            with self.assertRaisesRegex(ValueError, "fail-closed"):
                generate_exports(manifest, output_dir=output)
            self.assertFalse((output / SHOPIFY_CSV).exists())
            self.assertFalse((output / PIM_CSV).exists())

    def test_all_profile_writes_draft_shopify_pim_and_local_image_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            summary, export_manifest = generate_exports(
                manifest,
                output_dir=root / "exports",
                profile="all",
            )
            self.assertEqual(export_manifest.name, EXPORT_MANIFEST)
            self.assertEqual(summary["products"], 2)
            self.assertEqual(summary["confirmed_groups"], 2)
            self.assertEqual(summary["pending_groups"], 0)
            self.assertEqual(summary["shopify_status"], "draft")
            self.assertFalse(summary["shopify_published_on_online_store"])
            self.assertFalse(summary["publishing_enabled"])
            self.assertEqual(summary["network_calls_performed"], 0)
            self.assertFalse(summary["source_files_modified"])
            self.assertEqual(summary["public_image_urls_invented"], 0)

            with (export_manifest.parent / SHOPIFY_CSV).open(
                encoding="utf-8", newline=""
            ) as handle:
                shopify = list(csv.DictReader(handle))
            self.assertEqual(len(shopify), 2)
            self.assertEqual(shopify[0]["Status"], "draft")
            self.assertEqual(shopify[0]["Published on online store"], "false")
            self.assertEqual(shopify[0]["Option1 name"], "Default Title")
            self.assertEqual(shopify[0]["Option1 value"], "Default Title")
            self.assertEqual(shopify[0]["Price"], "399.00")
            self.assertNotIn("Product image URL", shopify[0])
            self.assertNotEqual(shopify[0]["URL handle"], shopify[1]["URL handle"])

            with (export_manifest.parent / PIM_CSV).open(
                encoding="utf-8", newline=""
            ) as handle:
                pim = list(csv.DictReader(handle))
            self.assertEqual(len(pim), 2)
            catalog_fields = json.loads(pim[0]["catalog_fields_json"])
            self.assertEqual(catalog_fields["SKU"], "ML-M100-A")

            with (export_manifest.parent / IMAGE_MANIFEST).open(
                encoding="utf-8", newline=""
            ) as handle:
                images = list(csv.DictReader(handle))
            self.assertEqual(len(images), 3)
            self.assertTrue(all(row["public_image_url"] == "" for row in images))
            self.assertTrue(all(row["status"] == "requires_upload" for row in images))

    def test_missing_or_non_numeric_price_blocks_shopify_but_not_pim(self):
        for unsafe_price in ("", "EGP 399", "$399"):
            with self.subTest(price=unsafe_price):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    manifest = self._manifest(root, first_price=unsafe_price)
                    shopify_output = root / "shopify-exports"
                    with self.assertRaisesRegex(ValueError, "blocking errors"):
                        generate_exports(
                            manifest,
                            output_dir=shopify_output,
                            profile="shopify",
                        )
                    self.assertFalse((shopify_output / SHOPIFY_CSV).exists())
                    self.assertTrue((shopify_output / VALIDATION_CSV).is_file())
                    with (shopify_output / VALIDATION_CSV).open(
                        encoding="utf-8", newline=""
                    ) as handle:
                        issues = list(csv.DictReader(handle))
                    self.assertTrue(
                        any(
                            row["severity"] == "error" and row["field"] == "price"
                            for row in issues
                        )
                    )

                    pim_output = root / "pim-exports"
                    summary, path = generate_exports(
                        manifest,
                        output_dir=pim_output,
                        profile="pim",
                    )
                    self.assertEqual(summary["shopify_status"], "not_generated")
                    self.assertTrue((path.parent / PIM_CSV).is_file())
                    self.assertFalse((path.parent / SHOPIFY_CSV).exists())

    def test_cli_export_is_standalone_and_performs_no_provider_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            output = root / "cli-exports"
            env = os.environ.copy()
            for name in list(env):
                if name.startswith("GEMINI_API_KEY") or name.startswith("OPENAI_API_KEY") or name.startswith("ANTHROPIC_API_KEY"):
                    env.pop(name, None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "product_sorter.py"),
                    "--export-catalog",
                    str(manifest),
                    "--export-output",
                    str(output),
                    "--export-profile",
                    "all",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertIn("Offline export only", result.stdout)
            payload = json.loads((output / EXPORT_MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(payload["network_calls_performed"], 0)
            self.assertFalse(payload["publishing_enabled"])


if __name__ == "__main__":
    unittest.main()
