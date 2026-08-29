import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter.ollama_local import (
    OllamaVisionProvider,
    _install_image_cache,
    discover_ollama_models,
)
from ai_product_photo_sorter.provider_selection import normalize_provider_sequence


class OllamaDiscoveryTests(unittest.TestCase):
    @patch("ai_product_photo_sorter.ollama_local.ollama_model_details")
    @patch("ai_product_photo_sorter.ollama_local._request_json")
    def test_discovery_returns_only_installed_vision_models(self, request_json, details):
        request_json.return_value = {
            "models": [
                {"name": "gemma4:latest"},
                {"name": "qwen-text:latest"},
            ]
        }
        details.side_effect = [
            {"capabilities": ["completion", "vision"]},
            {"capabilities": ["completion"]},
        ]

        models = discover_ollama_models("http://127.0.0.1:11434")

        self.assertEqual(["gemma4:latest"], models)
        request_json.assert_called_once()
        self.assertEqual(2, details.call_count)

    def test_local_alias_is_canonicalized_to_ollama(self):
        providers, corrections = normalize_provider_sequence("local,gemini")
        self.assertEqual(["ollama", "gemini"], providers)
        self.assertEqual([("local", "ollama")], corrections)


class OllamaInferenceTests(unittest.TestCase):
    @patch("ai_product_photo_sorter.ollama_local._request_json")
    def test_generate_sends_images_as_local_chat_and_records_usage(self, request_json):
        request_json.return_value = {
            "message": {"role": "assistant", "content": '{"items":[]}'},
            "prompt_eval_count": 123,
            "eval_count": 45,
            "total_duration": 1000,
            "load_duration": 200,
            "prompt_eval_duration": 300,
            "eval_duration": 500,
        }
        provider = OllamaVisionProvider(
            "gemma4:latest",
            "http://127.0.0.1:11434",
            keep_alive="15m",
            timeout=90,
        )
        photos = [SimpleNamespace(path=Path("one.jpg")), SimpleNamespace(path=Path("two.jpg"))]

        result = provider.generate("classify", photos, lambda path: path.name.encode("utf-8"))

        self.assertEqual('{"items":[]}', result)
        self.assertEqual({"input_tokens": 123, "output_tokens": 45}, provider.last_usage)
        kwargs = request_json.call_args.kwargs
        payload = kwargs["payload"]
        self.assertEqual("gemma4:latest", payload["model"])
        self.assertFalse(payload["stream"])
        self.assertEqual("json", payload["format"])
        self.assertEqual("15m", payload["keep_alive"])
        self.assertEqual(2, len(payload["messages"][0]["images"]))

    @patch("ai_product_photo_sorter.ollama_local.ollama_model_details")
    def test_validation_rejects_installed_text_only_model(self, details):
        details.return_value = {"capabilities": ["completion"]}
        provider = OllamaVisionProvider("text-only")
        ok, message = provider.validate()
        self.assertFalse(ok)
        self.assertIn("vision", message.lower())


class ImageCacheTests(unittest.TestCase):
    def test_encoded_image_cache_reuses_unchanged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.jpg"
            path.write_bytes(b"source")
            calls = []

            def compress(candidate):
                calls.append(candidate)
                return b"encoded"

            module = SimpleNamespace(compressed_image_bytes=compress)
            with patch.dict(os.environ, {"PRODUCT_SORTER_IMAGE_CACHE_ENTRIES": "4"}, clear=False):
                _install_image_cache(module)
                first = module.compressed_image_bytes(path)
                second = module.compressed_image_bytes(path)

            self.assertEqual(b"encoded", first)
            self.assertEqual(first, second)
            self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
