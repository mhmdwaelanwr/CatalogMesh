from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ai_product_photo_sorter.local_evidence import identifier_candidates, scan_source


class LocalEvidenceTests(unittest.TestCase):
    def _photos(self, root: Path, count: int = 3) -> Path:
        source = root / "photos"
        source.mkdir()
        for index in range(count):
            Image.new("RGB", (120, 80), (240, 240, 240)).save(
                source / f"IMG_{index:03d}.jpg", "JPEG"
            )
        return source

    def test_identifier_candidates_prioritize_barcode_and_labeled_ocr(self):
        candidates = identifier_candidates(
            [
                {"text": "SKU: ABC-1234", "score": 0.98},
                {"text": "Model MOUSE-X20", "score": 0.95},
                {"text": "random words", "score": 0.90},
            ],
            [{"text": "6221234567890", "format": "EAN13", "content_type": "Text"}],
        )
        values = [row["value"] for row in candidates]
        sources = {row["value"]: row["source"] for row in candidates}
        self.assertEqual(values[0], "6221234567890")
        self.assertEqual(sources["ABC-1234"], "ocr_labeled")
        self.assertIn("MOUSE-X20", values)

    def test_scan_writes_evidence_without_enabling_matching_or_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._photos(root)
            output = root / "evidence"

            def ocr(path: Path):
                index = int(path.stem.split("_")[-1])
                return [{"text": f"SKU: TEST-{index:03d}", "score": 0.99}]

            def barcode(path: Path):
                index = int(path.stem.split("_")[-1])
                return [
                    {
                        "text": f"62200000000{index}",
                        "format": "EAN13",
                        "content_type": "Text",
                    }
                ]

            summary, json_path, csv_path = scan_source(
                source,
                output_dir=output,
                ocr_reader=ocr,
                barcode_reader=barcode,
            )

            self.assertEqual(summary["photos"], 3)
            self.assertEqual(summary["ocr_photo_hits"], 3)
            self.assertEqual(summary["barcode_photo_hits"], 3)
            self.assertEqual(summary["candidate_photo_hits"], 3)
            self.assertFalse(summary["production_matching_enabled"])
            self.assertFalse(summary["production_routing_enabled"])
            self.assertTrue(json_path.is_file())
            self.assertTrue(csv_path.is_file())

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["photos"]), 3)
            self.assertIn("TEST-000", [
                row["value"] for row in payload["photos"][0]["identifier_candidates"]
            ])

    def test_one_backend_failure_is_recorded_per_photo_without_aborting_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._photos(root, count=2)

            def broken_ocr(path: Path):
                if path.name.endswith("001.jpg"):
                    raise RuntimeError("mock OCR failure")
                return [{"text": "SKU GOOD-100", "score": 0.9}]

            summary, json_path, _ = scan_source(
                source,
                output_dir=root / "evidence",
                use_barcode=False,
                ocr_reader=broken_ocr,
            )

            self.assertEqual(summary["photos"], 2)
            self.assertEqual(summary["photos_with_backend_errors"], 1)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            failed = [row for row in payload["photos"] if row["errors"]]
            self.assertEqual(len(failed), 1)
            self.assertIn("mock OCR failure", failed[0]["errors"][0])

    def test_disabling_both_backends_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._photos(root, count=1)
            with self.assertRaisesRegex(ValueError, "Enable at least one"):
                scan_source(
                    source,
                    output_dir=root / "evidence",
                    use_ocr=False,
                    use_barcode=False,
                )


if __name__ == "__main__":
    unittest.main()
