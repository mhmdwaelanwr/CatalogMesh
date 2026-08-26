import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from ai_product_photo_sorter import hardening
from sorter_core import CATEGORIES, build_outputs, compressed_image_bytes


class LargeCatalogHardeningTests(unittest.TestCase):
    def _item(self, source: Path, category: str = "mouse"):
        return {
            "path": source,
            "taken_at": datetime(2026, 8, 26, 10, 0, 0),
            "same_product_as_previous": False,
            "view": "front",
            "brand": "Test",
            "model": "One",
            "catalog_match": "",
            "confidence": 0.95,
            "reason": "visible package",
            "category": category,
        }

    def test_retail_taxonomy_covers_common_store_products(self):
        expected = {
            "hub", "stand", "power_bank", "smartwatch", "earbuds",
            "storage", "case", "screen_protector", "tool",
        }
        self.assertTrue(expected.issubset(CATEGORIES))

    def test_high_resolution_threshold_is_raised_but_not_disabled(self):
        self.assertEqual(Image.MAX_IMAGE_PIXELS, hardening.MAX_TRUSTED_IMAGE_PIXELS)
        self.assertGreater(Image.MAX_IMAGE_PIXELS, 108_576_768)
        self.assertIsNotNone(Image.MAX_IMAGE_PIXELS)

    def test_api_payload_is_bounded_to_1600_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large.jpg"
            Image.new("RGB", (3200, 2400), "white").save(source, quality=90)
            payload = compressed_image_bytes(source)
            output = Path(directory) / "payload.jpg"
            output.write_bytes(payload)
            with Image.open(output) as image:
                self.assertLessEqual(max(image.size), hardening.API_IMAGE_EDGE)
                self.assertEqual(image.mode, "RGB")

    @patch.dict(os.environ, {}, clear=True)
    def test_default_output_is_independent_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            destination = root / "destination.jpg"
            source.write_bytes(b"catalog-photo")

            mode = hardening._materialize(source, destination)

            self.assertEqual(mode, "copy")
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertFalse(os.path.samefile(source, destination))
            destination.write_bytes(b"edited-catalog-copy")
            self.assertEqual(source.read_bytes(), b"catalog-photo")

    @patch.dict(os.environ, {hardening.OUTPUT_MODE_ENV: "auto"}, clear=False)
    def test_auto_mode_falls_back_to_copy_when_links_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            destination = root / "destination.jpg"
            source.write_bytes(b"catalog-photo")

            with patch("ai_product_photo_sorter.hardening.os.link", side_effect=OSError("cross-device")), \
                    patch.object(Path, "symlink_to", side_effect=OSError("not permitted")), \
                    patch("ai_product_photo_sorter.hardening.shutil.copy2", wraps=shutil.copy2) as copy2:
                mode = hardening._materialize(source, destination)

            self.assertEqual(mode, "copy")
            copy2.assert_called_once_with(source, destination)
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    @patch.dict(os.environ, {hardening.OUTPUT_MODE_ENV: "copy"}, clear=False)
    def test_rebuild_removes_only_previous_managed_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            source.write_bytes(b"original-image-bytes")
            output = root / "Sorted_Products"
            manual = output / "manual-note.txt"
            output.mkdir()
            manual.write_text("keep me", encoding="utf-8")

            with patch("ai_product_photo_sorter.hardening._ensure_copy_capacity"):
                build_outputs([self._item(source, "mouse")], output, 0.75, False)
                old_destination = output / "mouse" / "Product_0001_Test_One" / "source.jpg"
                self.assertTrue(os.path.lexists(old_destination))

                build_outputs([self._item(source, "stand")], output, 0.75, False)

            new_destination = output / "stand" / "Product_0001_Test_One" / "source.jpg"
            self.assertFalse(os.path.lexists(old_destination))
            self.assertTrue(os.path.lexists(new_destination))
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"original-image-bytes")
            self.assertEqual(manual.read_text(encoding="utf-8"), "keep me")

            manifest = json.loads((output / hardening.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], 2)
            self.assertEqual(manifest["output_mode"], "copy")

    @patch.dict(os.environ, {hardening.OUTPUT_MODE_ENV: "copy"}, clear=False)
    def test_unrelated_exact_destination_is_preserved_and_collision_is_renamed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            source.write_bytes(b"original")
            output = root / "Sorted_Products"
            collision_dir = output / "mouse" / "Product_0001_Test_One"
            collision_dir.mkdir(parents=True)
            manual_collision = collision_dir / "source.jpg"
            manual_collision.write_bytes(b"manual-file")

            with patch("ai_product_photo_sorter.hardening._ensure_copy_capacity"):
                build_outputs([self._item(source)], output, 0.75, False)

            generated = collision_dir / "source__sorter_1.jpg"
            self.assertEqual(manual_collision.read_bytes(), b"manual-file")
            self.assertEqual(generated.read_bytes(), b"original")

            report = (output / "classification_report.csv").read_text(encoding="utf-8-sig")
            self.assertIn("output_filename", report)
            self.assertIn("source__sorter_1.jpg", report)

            with patch("ai_product_photo_sorter.hardening._ensure_copy_capacity"):
                build_outputs([self._item(source, "stand")], output, 0.75, False)
            self.assertEqual(manual_collision.read_bytes(), b"manual-file")

    @patch.dict(os.environ, {hardening.OUTPUT_MODE_ENV: "copy"}, clear=False)
    def test_copy_capacity_check_fails_before_copying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            source.write_bytes(b"x" * 100)
            output = root / "Sorted_Products"
            output.mkdir()

            with patch(
                "ai_product_photo_sorter.hardening.shutil.disk_usage",
                return_value=SimpleNamespace(free=50),
            ):
                with self.assertRaisesRegex(RuntimeError, "Not enough free space"):
                    hardening._ensure_copy_capacity([self._item(source)], output)

    @patch.dict(os.environ, {hardening.OUTPUT_MODE_ENV: "not-a-mode"}, clear=False)
    def test_invalid_output_mode_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid PRODUCT_SORTER_OUTPUT_MODE"):
            hardening._output_mode()


if __name__ == "__main__":
    unittest.main()
