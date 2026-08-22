import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from model_catalog import choose_from_list, discover_models, refresh_catalog


def response(payload):
    handle = MagicMock()
    handle.read.return_value = json.dumps(payload).encode()
    handle.__enter__.return_value = handle
    return handle


class ModelCatalogTests(unittest.TestCase):
    @patch("model_catalog.urllib.request.urlopen")
    def test_gemini_discovery_keeps_generate_content_models(self, mocked):
        mocked.return_value = response({"models": [
            {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-only", "supportedGenerationMethods": ["embedContent"]},
        ]})
        self.assertEqual(discover_models("gemini", "secret"), ["gemini-3.6-flash"])

    @patch("model_catalog.urllib.request.urlopen")
    def test_openai_discovery_returns_every_visible_model(self, mocked):
        mocked.return_value = response({"data": [{"id": "gpt-b"}, {"id": "gpt-a"}]})
        self.assertEqual(discover_models("openai", "secret"), ["gpt-a", "gpt-b"])

    @patch("model_catalog.discover_models", return_value=["new-a", "new-b"])
    def test_refresh_writes_models_without_api_key(self, mocked):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text('{"schema_version":1,"providers":{"gemini":{"default":"old","models":["old"]}}}')
            refresh_catalog("gemini", "top-secret", path=path)
            text = path.read_text()
            self.assertIn("new-a", text)
            self.assertNotIn("top-secret", text)

    @patch("builtins.input", return_value="2")
    def test_user_can_choose_a_numbered_model(self, mocked):
        self.assertEqual(choose_from_list("gemini", "first", ["first", "second"]), "second")


if __name__ == "__main__":
    unittest.main()
