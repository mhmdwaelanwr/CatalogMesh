import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter.key_validation import apply_key_validation_hardening


class OllamaKeyValidationTests(unittest.TestCase):
    def test_local_pool_is_kept_even_when_endpoint_validation_returns_http_400(self):
        local_client = object()
        pool = SimpleNamespace(
            name="ollama",
            clients=[local_client],
            index=0,
            validate_all=lambda: [(False, "Ollama HTTP 400 Bad Request: model missing")],
        )
        captured = {}

        class GeminiPool:
            def __init__(self, keys):
                self.clients = list(keys)

        module = SimpleNamespace()
        module.load_api_keys = lambda: []
        module.validate_gemini_key = lambda key: (True, "ok")
        module.GeminiClientPool = GeminiPool
        module.configured_rest_providers = lambda: [pool]

        def base_main():
            captured["pools"] = module.configured_rest_providers()
            return 0

        module.main = base_main
        apply_key_validation_hardening(module)

        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "ollama", "VALIDATE_KEYS": "true"},
            clear=False,
        ):
            self.assertEqual(0, module.main())

        self.assertEqual([pool], captured["pools"])
        self.assertEqual([local_client], pool.clients)
        self.assertEqual(
            [(False, "Ollama HTTP 400 Bad Request: model missing")],
            pool.validate_all(),
        )


if __name__ == "__main__":
    unittest.main()
