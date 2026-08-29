import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter import ollama_local


class _Photo:
    def __init__(self, path: Path):
        self.path = path


class OllamaLocalTests(unittest.TestCase):
    def test_classification_schema_requires_exact_photo_count(self):
        schema = ollama_local._classification_schema(6)
        items = schema["properties"]["items"]
        self.assertEqual(6, items["minItems"])
        self.assertEqual(6, items["maxItems"])
        self.assertFalse(items["items"]["additionalProperties"])
        self.assertIn("filename", items["items"]["required"])
        self.assertIn("confidence", items["items"]["required"])

    @patch("ai_product_photo_sorter.ollama_local._request_json")
    def test_model_discovery_returns_only_vision_models(self, request_json):
        def response(path, *, payload=None, **kwargs):
            if path == "/api/tags":
                return {
                    "models": [
                        {"name": "gemma4:latest"},
                        {"name": "embeddinggemma:latest"},
                        {"name": "qwen-vl:latest"},
                    ]
                }
            model = payload["model"]
            if model in {"gemma4:latest", "qwen-vl:latest"}:
                return {"capabilities": ["completion", "vision"]}
            return {"capabilities": ["embedding"]}

        request_json.side_effect = response
        models = ollama_local.discover_ollama_models("http://127.0.0.1:11434")
        self.assertEqual(["gemma4:latest", "qwen-vl:latest"], models)

    @patch("ai_product_photo_sorter.ollama_local._request_json")
    def test_generate_sends_images_structured_schema_and_keep_alive(self, request_json):
        request_json.return_value = {
            "message": {"content": json.dumps({"items": [{
                "filename": "a.jpg",
                "same_product_as_previous": False,
                "category": "mouse",
                "view": "front",
                "brand": "",
                "model": "",
                "catalog_match": "",
                "confidence": 0.9,
                "reason": "visible product",
            }]})},
            "prompt_eval_count": 120,
            "eval_count": 40,
            "total_duration": 1000,
            "load_duration": 100,
            "prompt_eval_duration": 400,
            "eval_duration": 500,
        }
        provider = ollama_local.OllamaVisionProvider(
            "gemma4", "http://localhost:11434", "15m", 60
        )
        photo = _Photo(Path("a.jpg"))
        result = provider.generate("classify", [photo], lambda path: b"jpeg-bytes")
        self.assertIn('"items"', result)
        payload = request_json.call_args.kwargs["payload"]
        self.assertEqual("gemma4", payload["model"])
        self.assertEqual(False, payload["stream"])
        self.assertEqual("15m", payload["keep_alive"])
        self.assertIsInstance(payload["format"], dict)
        self.assertEqual(1, payload["format"]["properties"]["items"]["minItems"])
        self.assertEqual(1, len(payload["messages"][0]["images"]))
        self.assertEqual(120, provider.last_usage["input_tokens"])
        self.assertEqual(40, provider.last_usage["output_tokens"])
        self.assertEqual(100, provider.last_metrics["load_duration_ns"])

    def test_image_cache_reuses_compressed_overlap_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            path.write_bytes(b"source")
            calls = []
            module = SimpleNamespace(
                compressed_image_bytes=lambda value: calls.append(value) or b"encoded"
            )
            with patch.dict(os.environ, {"PRODUCT_SORTER_IMAGE_CACHE_ENTRIES": "4"}, clear=False):
                ollama_local._install_image_cache(module)
                first = module.compressed_image_bytes(path)
                second = module.compressed_image_bytes(path)
            self.assertEqual(b"encoded", first)
            self.assertEqual(first, second)
            self.assertEqual(1, len(calls))
            self.assertEqual(2, module.IMAGE_CACHE_STATS["requests"])
            self.assertEqual(1, module.IMAGE_CACHE_STATS["hits"])
            self.assertEqual(1, module.IMAGE_CACHE_STATS["misses"])

    def test_apply_adds_local_provider_and_bypasses_internet_gate(self):
        module = SimpleNamespace(
            configured_rest_providers=lambda: [],
            require_internet=lambda output: False,
            call_rest_pool=lambda *args, **kwargs: {"cloud": True},
            compressed_image_bytes=lambda path: b"encoded",
            parse_args=lambda env_file: argparse.Namespace(source=Path(".")),
            call_rest_provider=lambda *args, **kwargs: {"items": []},
        )
        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "ollama", "OLLAMA_MODEL": "gemma4"},
            clear=False,
        ):
            ollama_local.apply_ollama_local(module)
            pools = module.configured_rest_providers()
            self.assertEqual(1, len(pools))
            self.assertEqual("ollama", pools[0].name)
            self.assertTrue(module.require_internet(Path(".")))

    def test_local_cli_flag_selects_ollama_without_api_key(self):
        captured = {}

        def base_parse(env_file):
            captured["argv"] = list(sys.argv)
            return argparse.Namespace(source=Path("."))

        module = SimpleNamespace(
            configured_rest_providers=lambda: [],
            require_internet=lambda output: True,
            call_rest_pool=lambda *args, **kwargs: {},
            compressed_image_bytes=lambda path: b"encoded",
            parse_args=base_parse,
            call_rest_provider=lambda *args, **kwargs: {},
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(
            sys, "argv", ["product-sorter", "--local", "--ollama-model", "gemma4", "--dry-run"]
        ):
            ollama_local.apply_ollama_local(module)
            module.parse_args(Path(".env"))
            self.assertEqual("ollama", os.environ["AI_PROVIDERS"])
            self.assertEqual("ollama", os.environ["AI_PROVIDER"])
            self.assertEqual("gemma4", os.environ["OLLAMA_MODEL"])
            self.assertEqual(["product-sorter", "--dry-run"], captured["argv"])


if __name__ == "__main__":
    unittest.main()
