from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

from ai_product_photo_sorter.sku_matching import (
    AUDIT_NAME,
    CANDIDATES_NAME,
    CONFIRMED_NAME,
    MANIFEST_NAME,
    clear_confirmation,
    confirm_candidate,
    generate_candidates,
    load_catalog_rows,
    load_match_manifest,
    rank_catalog_rows,
)


ROOT = Path(__file__).resolve().parent.parent


class SkuMatchingTests(unittest.TestCase):
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
                    "group_id": "Product_0001_Mouse_M100",
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
                    "group_id": "Product_0002_Keyboard_K200",
                    "category": "keyboard",
                    "brand": "MockLab",
                    "model": "K200",
                    "photo_count": "2",
                    "filenames": "B_front.jpg | B_back.jpg",
                    "views": "front | back",
                    "notes": "approved",
                }
            )
        return path

    def _catalog(self, root: Path) -> Path:
        path = root / "catalog.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Catalog"
        sheet.append(["SKU", "Barcode", "Brand", "Model", "Category", "Name", "Price"])
        sheet.append(["ML-M100-BLK", "6221111000017", "MockLab", "M100", "mouse", "MockLab M100 Mouse", 399])
        sheet.append(["ML-M110-BLK", "6221111000024", "MockLab", "M110", "mouse", "MockLab M110 Mouse", 429])
        sheet.append(["ML-K200", "6221111000031", "MockLab", "K200", "keyboard", "MockLab K200 Keyboard", 599])
        sheet.append(["OTHER-900", "6221111000048", "Other", "Z900", "mouse", "Generic Mouse", 199])
        workbook.save(path)
        workbook.close()
        return path

    def _evidence(self, root: Path) -> Path:
        path = root / "local_catalog_evidence.json"
        payload = {
            "summary": {
                "mode": "local_evidence",
                "production_matching_enabled": False,
            },
            "photos": [
                {
                    "filename": "A_front.jpg",
                    "ocr": [{"text": "SKU: ML-M100-BLK", "score": 0.99}],
                    "barcodes": [{"text": "6221111000017", "format": "EAN13", "content_type": "Text"}],
                    "identifier_candidates": [
                        {"value": "6221111000017", "source": "barcode"},
                        {"value": "ML-M100-BLK", "source": "ocr_labeled"},
                    ],
                    "errors": [],
                },
                {
                    "filename": "A_back.jpg",
                    "ocr": [{"text": "MODEL M100", "score": 0.98}],
                    "barcodes": [],
                    "identifier_candidates": [{"value": "M100", "source": "ocr_labeled"}],
                    "errors": [],
                },
                {
                    "filename": "B_front.jpg",
                    "ocr": [{"text": "SKU ML-K200", "score": 0.99}],
                    "barcodes": [{"text": "6221111000031", "format": "EAN13", "content_type": "Text"}],
                    "identifier_candidates": [
                        {"value": "6221111000031", "source": "barcode"},
                        {"value": "ML-K200", "source": "ocr_labeled"},
                    ],
                    "errors": [],
                },
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_structured_xlsx_catalog_preserves_headers_and_row_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = load_catalog_rows(self._catalog(root))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["row_id"], "Catalog!R2")
            self.assertEqual(rows[0]["fields"]["sku"], "ML-M100-BLK")
            self.assertEqual(rows[0]["fields"]["barcode"], "6221111000017")
            self.assertEqual(rows[2]["fields"]["model"], "K200")

    def test_exact_barcode_and_identifier_rank_correct_row_first_but_never_auto_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, path = generate_candidates(
                self._approved(root),
                self._catalog(root),
                evidence_json=self._evidence(root),
                output_dir=root / "matching",
                top_k=3,
            )
            self.assertEqual(path.name, MANIFEST_NAME)
            self.assertTrue((path.parent / CANDIDATES_NAME).is_file())
            self.assertTrue((path.parent / CONFIRMED_NAME).is_file())
            self.assertFalse(manifest["summary"]["automatic_matching_enabled"])
            self.assertTrue(manifest["summary"]["human_confirmation_required"])
            self.assertFalse(manifest["summary"]["publishing_enabled"])
            self.assertEqual(manifest["summary"]["confirmed_groups"], 0)
            self.assertFalse(manifest["summary"]["catalog_ready_for_export"])

            first, second = manifest["groups"]
            self.assertEqual(first["candidates"][0]["row_id"], "Catalog!R2")
            self.assertEqual(first["candidates"][0]["tier"], "exact_barcode")
            self.assertEqual(second["candidates"][0]["row_id"], "Catalog!R4")
            self.assertEqual(second["candidates"][0]["tier"], "exact_barcode")
            self.assertEqual(first["decision"]["status"], "pending")
            self.assertEqual(second["decision"]["status"], "pending")

            with (path.parent / CONFIRMED_NAME).open(encoding="utf-8-sig", newline="") as handle:
                confirmed = list(csv.DictReader(handle))
            self.assertEqual(confirmed, [])

    def test_group_evidence_uses_only_filenames_from_that_approved_group(self):
        group = {
            "group_id": "G1",
            "category": "mouse",
            "brand": "MockLab",
            "model": "",
            "filenames": ["A.jpg"],
            "notes": "",
        }
        evidence = {
            "barcodes": ["1111111111111"],
            "labeled_identifiers": [],
            "ocr_tokens": [],
            "evidence_photos": 1,
        }
        catalog = [
            {
                "row_id": "Catalog!R2",
                "fields": {"sku": "A1", "barcode": "1111111111111", "name": "Mouse A"},
                "search_text": "A1 | 1111111111111 | Mouse A",
            },
            {
                "row_id": "Catalog!R3",
                "fields": {"sku": "B1", "barcode": "2222222222222", "name": "Mouse B"},
                "search_text": "B1 | 2222222222222 | Mouse B",
            },
        ]
        ranked = rank_catalog_rows(group, evidence, catalog, top_k=2)
        self.assertEqual(ranked[0]["row_id"], "Catalog!R2")
        self.assertEqual(ranked[0]["tier"], "exact_barcode")

    def test_confirmation_is_explicit_audited_and_clearable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, path = generate_candidates(
                self._approved(root),
                self._catalog(root),
                evidence_json=self._evidence(root),
                output_dir=root / "matching",
            )
            manifest, _ = confirm_candidate(path, "Product_0001_Mouse_M100", "Catalog!R2")
            self.assertEqual(manifest["revision"], 1)
            self.assertEqual(manifest["summary"]["confirmed_groups"], 1)
            self.assertFalse(manifest["summary"]["catalog_ready_for_export"])
            group = manifest["groups"][0]
            self.assertEqual(group["decision"]["status"], "confirmed")
            self.assertEqual(group["decision"]["row_id"], "Catalog!R2")

            with (path.parent / CONFIRMED_NAME).open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["group_id"], "Product_0001_Mouse_M100")
            self.assertEqual(rows[0]["row_id"], "Catalog!R2")

            events = [
                json.loads(line)
                for line in (path.parent / AUDIT_NAME).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[0]["action"], "confirm")
            self.assertFalse(events[0]["automatic"])

            manifest, _ = clear_confirmation(path, "Product_0001_Mouse_M100")
            self.assertEqual(manifest["revision"], 2)
            self.assertEqual(manifest["summary"]["confirmed_groups"], 0)
            events = [
                json.loads(line)
                for line in (path.parent / AUDIT_NAME).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([event["action"] for event in events], ["confirm", "clear_confirmation"])

    def test_confirmation_rejects_catalog_row_not_in_current_candidate_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, path = generate_candidates(
                self._approved(root),
                self._catalog(root),
                evidence_json=self._evidence(root),
                output_dir=root / "matching",
                top_k=1,
            )
            with self.assertRaisesRegex(ValueError, "not a current candidate"):
                confirm_candidate(path, "Product_0001_Mouse_M100", "Catalog!R5")
            manifest, _ = load_match_manifest(path)
            self.assertEqual(manifest["revision"], 0)
            self.assertEqual(manifest["summary"]["confirmed_groups"], 0)

    def test_cli_candidate_and_confirmation_work_without_ai_provider_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = self._approved(root)
            catalog = self._catalog(root)
            evidence = self._evidence(root)
            output = root / "matching"

            generated = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "product_sorter.py"),
                    "--sku-match",
                    str(approved),
                    "--sku-catalog",
                    str(catalog),
                    "--sku-evidence",
                    str(evidence),
                    "--sku-output",
                    str(output),
                    "--sku-top-k",
                    "3",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={},
            )
            self.assertEqual(generated.returncode, 0, generated.stderr or generated.stdout)
            self.assertIn("Suggestions only", generated.stdout)
            manifest_path = output / MANIFEST_NAME
            self.assertTrue(manifest_path.is_file())

            confirmed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "product_sorter.py"),
                    "--sku-confirm",
                    str(manifest_path),
                    "--sku-group",
                    "Product_0001_Mouse_M100",
                    "--sku-row",
                    "Catalog!R2",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={},
            )
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr or confirmed.stdout)
            self.assertIn("Confirmed catalog candidate", confirmed.stdout)
            manifest, _ = load_match_manifest(manifest_path)
            self.assertEqual(manifest["summary"]["confirmed_groups"], 1)


if __name__ == "__main__":
    unittest.main()
