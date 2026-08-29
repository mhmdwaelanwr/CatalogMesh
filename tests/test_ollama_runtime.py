import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter.ollama_local import apply_ollama_local


class OllamaRuntimeTests(unittest.TestCase):
    def make_module(self):
        seen = {}

        def parse_args(env_file):
            seen["argv"] = list(sys.argv)
            return SimpleNamespace(env_file=env_file)

        module = SimpleNamespace(
            parse_args=parse_args,
            configured_rest_providers=lambda: [],
            require_internet=lambda output: False,
            call_rest_pool=lambda *args, **kwargs: {"cloud": True},
            call_rest_provider=lambda *args, **kwargs: {"items": []},
            compressed_image_bytes=lambda path: b"encoded",
        )
        return module, seen

    def test_local_cli_flag_selects_ollama_and_strips_extension_flags(self):
        module, seen = self.make_module()
        apply_ollama_local(module)
        argv = [
            "product-sorter",
            "--local",
            "--ollama-model",
            "gemma4:latest",
            "--source",
            "/photos",
        ]
        with patch.object(sys, "argv", argv), patch.dict(os.environ, {}, clear=False):
            module.parse_args(Path(".env"))
            self.assertEqual("ollama", os.environ["AI_PROVIDERS"])
            self.assertEqual("gemma4:latest", os.environ["OLLAMA_MODEL"])
        self.assertEqual(["product-sorter", "--source", "/photos"], seen["argv"])

    def test_local_provider_does_not_require_public_internet(self):
        module, _ = self.make_module()
        apply_ollama_local(module)
        with patch.dict(os.environ, {"AI_PROVIDERS": "ollama"}, clear=False):
            self.assertTrue(module.require_internet(Path("output")))
            providers = module.configured_rest_providers()
        self.assertEqual(1, len(providers))
        self.assertEqual("ollama", providers[0].name)

    def test_cloud_only_mode_keeps_existing_connectivity_preflight(self):
        module, _ = self.make_module()
        apply_ollama_local(module)
        with patch.dict(os.environ, {"AI_PROVIDERS": "gemini"}, clear=False):
            self.assertFalse(module.require_internet(Path("output")))
            self.assertEqual([], module.configured_rest_providers())


if __name__ == "__main__":
    unittest.main()
