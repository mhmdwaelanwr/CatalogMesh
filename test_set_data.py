import os
import tempfile
import unittest
from pathlib import Path

from set_data import build_env_text, read_env, save_env


class SetDataTests(unittest.TestCase):
    def test_save_and_read_env(self):
        values = {
            "GEMINI_API_KEY_1": "secret-key",
            "PRODUCT_SOURCE": "/tmp/Product Photos",
            "PRODUCT_OUTPUT": "/tmp/Sorted Products",
            "BATCH_SIZE": "6",
            "CONFIDENCE": "0.75",
            "MAX_RETRIES": "5",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            save_env(values, path)
            loaded = read_env(path)
            self.assertEqual(loaded["GEMINI_API_KEY_1"], "secret-key")
            self.assertEqual(loaded["PRODUCT_SOURCE"], "/tmp/Product Photos")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_env_text_never_contains_python_execution(self):
        text = build_env_text({"PRODUCT_SOURCE": "/tmp/photos"})
        self.assertIn("PRODUCT_SOURCE=/tmp/photos", text)
        self.assertNotIn("import ", text)


if __name__ == "__main__":
    unittest.main()
