import io
import os
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ai_product_photo_sorter.key_validation import (
    _definitively_invalid,
    apply_key_validation_hardening,
)


class FakeGeminiPool:
    def __init__(self, keys):
        self.clients = list(keys)
        self.index = 0


class FakeRestClient:
    def __init__(self, label):
        self.label = label


class FakeRestPool:
    def __init__(self, results):
        self.name = "openai"
        self.clients = [FakeRestClient(label) for label, _ in results]
        self._results = [result for _, result in results]
        self.index = 0
        self.validate_calls = 0

    def validate_all(self):
        self.validate_calls += 1
        return list(self._results)


class KeyValidationHardeningTests(unittest.TestCase):
    def test_definitive_credential_failures_are_distinguished_from_transient_errors(self):
        for detail in (
            "HTTP 400 Bad Request",
            "HTTP 401 Unauthorized",
            "HTTP 403 Forbidden",
            "API_KEY_INVALID",
            "API key not valid",
            "Unauthenticated",
        ):
            with self.subTest(detail=detail):
                self.assertTrue(_definitively_invalid(detail))

        for detail in (
            "HTTP 429 Too Many Requests",
            "timed out",
            "temporary DNS failure",
            "HTTP 500 Internal Server Error",
            "connection reset",
        ):
            with self.subTest(detail=detail):
                self.assertFalse(_definitively_invalid(detail))

    def test_gemini_rejects_invalid_key_but_keeps_inconclusive_key(self):
        calls = []
        observed = {}

        def validate(key):
            calls.append(key)
            return {
                "good": (True, "ok"),
                "bad": (False, "HTTP 401 Unauthorized"),
                "flaky": (False, "timed out"),
            }[key]

        module = types.SimpleNamespace()
        module.load_api_keys = lambda: ["good", "bad", "flaky"]
        module.validate_gemini_key = validate
        module.GeminiClientPool = FakeGeminiPool
        module.configured_rest_providers = lambda: []

        def base_main():
            keys = module.load_api_keys()
            pool = module.GeminiClientPool(keys)
            observed["clients"] = list(pool.clients)
            observed["statuses"] = [module.validate_gemini_key(key) for key in keys]
            observed["truthy"] = bool(pool)
            return 0

        module.main = base_main
        apply_key_validation_hardening(module)

        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "gemini", "VALIDATE_KEYS": "true"},
            clear=False,
        ), patch("sys.argv", ["product-sorter"]), redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(), 0)

        self.assertEqual(observed["clients"], ["good", "flaky"])
        self.assertTrue(observed["truthy"])
        self.assertEqual(calls, ["good", "bad", "flaky"])
        self.assertEqual(observed["statuses"][0], (True, "ok"))
        self.assertEqual(observed["statuses"][1], (False, "HTTP 401 Unauthorized"))
        self.assertFalse(observed["statuses"][2][0])
        self.assertIn("validation inconclusive", observed["statuses"][2][1])

    def test_all_definitively_invalid_gemini_keys_make_pool_false(self):
        observed = {}
        module = types.SimpleNamespace()
        module.load_api_keys = lambda: ["bad-1", "bad-2"]
        module.validate_gemini_key = lambda key: (False, "HTTP 403 Forbidden")
        module.GeminiClientPool = FakeGeminiPool
        module.configured_rest_providers = lambda: []

        def base_main():
            pool = module.GeminiClientPool(module.load_api_keys())
            observed["clients"] = list(pool.clients)
            observed["truthy"] = bool(pool)
            return 2 if not pool else 0

        module.main = base_main
        apply_key_validation_hardening(module)

        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "gemini", "VALIDATE_KEYS": "true"},
            clear=False,
        ), patch("sys.argv", ["product-sorter"]), redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(), 2)

        self.assertEqual(observed["clients"], [])
        self.assertFalse(observed["truthy"])

    def test_rest_pool_prunes_invalid_and_keeps_transient_validation_failure(self):
        pool = FakeRestPool(
            [
                ("good", (True, "ok")),
                ("bad", (False, "HTTP 401 Unauthorized")),
                ("flaky", (False, "HTTP 429 Too Many Requests")),
            ]
        )
        observed = {}
        module = types.SimpleNamespace()
        module.load_api_keys = lambda: []
        module.validate_gemini_key = lambda key: (True, "ok")
        module.GeminiClientPool = FakeGeminiPool
        module.configured_rest_providers = lambda: [pool]

        def base_main():
            providers = module.configured_rest_providers()
            observed["providers"] = providers
            observed["clients"] = [client.label for client in providers[0].clients]
            observed["statuses"] = providers[0].validate_all()
            return 0

        module.main = base_main
        apply_key_validation_hardening(module)

        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "openai", "VALIDATE_KEYS": "true"},
            clear=False,
        ), patch("sys.argv", ["product-sorter"]), redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(), 0)

        self.assertEqual(observed["clients"], ["good", "flaky"])
        self.assertEqual(pool.validate_calls, 1)
        self.assertEqual(observed["statuses"][0], (True, "ok"))
        self.assertFalse(observed["statuses"][1][0])
        self.assertIn("validation inconclusive", observed["statuses"][1][1])

    def test_validation_disabled_preserves_original_pool_without_network_validation(self):
        calls = []
        observed = {}

        def validate(key):
            calls.append(key)
            return False, "HTTP 401 Unauthorized"

        module = types.SimpleNamespace()
        module.load_api_keys = lambda: ["bad"]
        module.validate_gemini_key = validate
        module.GeminiClientPool = FakeGeminiPool
        module.configured_rest_providers = lambda: []

        def base_main():
            keys = module.load_api_keys()
            pool = module.GeminiClientPool(keys)
            observed["clients"] = list(pool.clients)
            return 0

        module.main = base_main
        apply_key_validation_hardening(module)

        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "gemini", "VALIDATE_KEYS": "false"},
            clear=False,
        ), patch("sys.argv", ["product-sorter"]), redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(), 0)

        self.assertEqual(observed["clients"], ["bad"])
        self.assertEqual(calls, [])

    def test_unused_gemini_keys_are_not_loaded_for_openai_only_run(self):
        observed = {}
        module = types.SimpleNamespace()
        module.load_api_keys = lambda: ["unused-gemini"]
        module.validate_gemini_key = lambda key: (True, "ok")
        module.GeminiClientPool = FakeGeminiPool
        module.configured_rest_providers = lambda: []

        def base_main():
            observed["keys"] = module.load_api_keys()
            return 0

        module.main = base_main
        apply_key_validation_hardening(module)

        with patch.dict(
            os.environ,
            {"AI_PROVIDERS": "openai", "VALIDATE_KEYS": "true"},
            clear=False,
        ), patch("sys.argv", ["product-sorter"]):
            self.assertEqual(module.main(), 0)

        self.assertEqual(observed["keys"], [])


if __name__ == "__main__":
    unittest.main()
