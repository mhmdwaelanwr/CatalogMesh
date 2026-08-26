import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sorter_core import (
    DYNAMIC_CATEGORIES,
    Photo,
    build_outputs,
    cached_batches,
    connect_db,
    normalize_response,
    prompt_for,
)


class DynamicTaxonomyTests(unittest.TestCase):
    def setUp(self):
        DYNAMIC_CATEGORIES.clear()

    def test_new_ai_category_is_accepted_and_normalized(self):
        photos = [Photo(Path("one.jpg"), datetime(2026, 8, 26, 10, 0, 0))]
        raw = json.dumps({
            "items": [{
                "filename": "one.jpg",
                "same_product_as_previous": False,
                "category": "Phone Holder / Stand",
                "view": "front",
                "brand": "",
                "model": "",
                "catalog_match": "",
                "confidence": 0.91,
                "reason": "visible product type",
            }]
        })

        result = normalize_response(raw, photos)

        self.assertEqual(result["items"][0]["category"], "phone_holder_stand")
        self.assertIn("phone_holder_stand", DYNAMIC_CATEGORIES)

    def test_later_prompt_reuses_categories_learned_from_earlier_batch(self):
        first = [Photo(Path("first.jpg"), datetime(2026, 8, 26, 10, 0, 0))]
        normalize_response(json.dumps({
            "items": [{
                "filename": "first.jpg",
                "category": "Memory Card Reader",
                "confidence": 0.9,
            }]
        }), first)

        second = [Photo(Path("second.jpg"), datetime(2026, 8, 26, 10, 1, 0))]
        prompt = prompt_for(second, "")

        self.assertIn("memory_card_reader", prompt)
        self.assertIn("category list is NOT fixed", prompt)
        self.assertIn("CREATE a concise new category", prompt)
        self.assertIn("Reuse an established category EXACTLY", prompt)

    def test_cached_batches_restore_taxonomy_after_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            db = connect_db(Path(directory) / "progress.sqlite3")
            response = {
                "items": [{
                    "filename": "cached.jpg",
                    "category": "soldering_iron",
                    "confidence": 0.95,
                }]
            }
            db.execute(
                "INSERT INTO batches VALUES (?, ?, ?, ?, ?)",
                (
                    "batch-key",
                    "model",
                    '["cached.jpg"]',
                    json.dumps(response),
                    datetime.now().isoformat(),
                ),
            )
            db.commit()

            cached_batches(db)
            db.close()

        self.assertIn("soldering_iron", DYNAMIC_CATEGORIES)

    def test_other_is_not_treated_as_a_learned_taxonomy_category(self):
        photos = [Photo(Path("one.jpg"), datetime(2026, 8, 26, 10, 0, 0))]
        normalize_response(json.dumps({
            "items": [{
                "filename": "one.jpg",
                "category": "unknown",
                "confidence": 0.2,
            }]
        }), photos)

        self.assertNotIn("other", DYNAMIC_CATEGORIES)

    def test_build_writes_observed_category_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            source.write_bytes(b"photo-bytes")
            output = root / "Sorted_Products"
            item = {
                "path": source,
                "taken_at": datetime(2026, 8, 26, 10, 0, 0),
                "same_product_as_previous": False,
                "category": "usb_test_meter",
                "view": "front",
                "brand": "",
                "model": "",
                "catalog_match": "",
                "confidence": 0.95,
                "reason": "visible meter",
            }

            with patch.dict(os.environ, {"PRODUCT_SORTER_OUTPUT_MODE": "copy"}):
                build_outputs([item], output, 0.75, False)

            registry = json.loads(
                (output / "category_registry.json").read_text(encoding="utf-8")
            )

        self.assertEqual(registry["mode"], "ai_dynamic")
        self.assertEqual(registry["categories"], ["usb_test_meter"])
        self.assertEqual(registry["category_count"], 1)


if __name__ == "__main__":
    unittest.main()
