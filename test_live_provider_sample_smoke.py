import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import live_provider_sample_smoke as smoke


class LiveProviderSampleSmokeTests(unittest.TestCase):
    def test_make_samples_creates_two_jpegs(self):
        with tempfile.TemporaryDirectory() as tmp:
            photos = smoke.make_samples(Path(tmp))
            self.assertEqual(2, len(photos))
            self.assertEqual({"synthetic_product_front.jpg", "synthetic_product_back.jpg"}, {p.path.name for p in photos})
            self.assertTrue(all(p.path.is_file() and p.path.stat().st_size > 0 for p in photos))

    def test_verify_response_requires_both_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            photos = smoke.make_samples(Path(tmp))
            response = {"items": [{"filename": p.path.name} for p in photos]}
            smoke.verify_response("test", response, photos)
            with self.assertRaises(RuntimeError):
                smoke.verify_response("test", {"items": response["items"][:1]}, photos)

    def test_requested_providers_filters_unknown_and_duplicates(self):
        with patch.dict(os.environ, {"AI_PROVIDERS": "gemini, openai,gemini,unknown"}, clear=False):
            self.assertEqual(["gemini", "openai"], smoke.requested_providers())

    def test_redact_error_hides_api_key_values(self):
        secret = "test-secret-value-that-must-not-leak"
        with patch.dict(os.environ, {"GEMINI_API_KEY": secret}, clear=False):
            text = smoke.redact_error(RuntimeError(f"provider rejected {secret}"))
        self.assertNotIn(secret, text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
