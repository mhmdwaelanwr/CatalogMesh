import io
import os
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from scripts.smoke import live_api_smoke as smoke


class LiveApiSmokeTests(unittest.TestCase):
    def test_safe_reason_redacts_openai_style_key_fragment(self):
        message = (
            "HTTP 401 Unauthorized: Incorrect API key provided: "
            "sk-example********************************suffix. See docs."
        )
        text = smoke.safe_reason(message)
        self.assertIn("HTTP 401 Unauthorized", text)
        self.assertIn("[REDACTED]", text)
        self.assertNotIn("sk-example", text)
        self.assertNotIn("suffix", text)

    def test_safe_reason_redacts_raw_anthropic_style_key(self):
        secret = "sk-ant-api03-exampleexampleexampleexample"
        text = smoke.safe_reason(f"API key provided: {secret}")
        self.assertNotIn(secret, text)
        self.assertIn("[REDACTED]", text)

    def test_requested_providers_uses_requested_chain(self):
        with patch.dict(os.environ, {"AI_PROVIDERS": "openai, anthropic"}, clear=False):
            self.assertEqual(["openai", "anthropic"], smoke.requested_providers())

    def test_openai_only_run_does_not_validate_unused_gemini_keys(self):
        provider = SimpleNamespace(
            name="openai",
            validate_all=lambda: [(False, "HTTP 401 Unauthorized: invalid key")],
        )
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"AI_PROVIDERS": "openai"}, clear=False),
            patch.object(smoke, "load_env_file"),
            patch.object(smoke, "load_api_keys") as load_gemini,
            patch.object(smoke, "configured_rest_providers", return_value=[provider]),
            redirect_stdout(output),
        ):
            code = smoke.main()

        self.assertEqual(1, code)
        load_gemini.assert_not_called()
        self.assertIn("openai key 1: FAILED", output.getvalue())

    def test_no_keys_for_requested_provider_returns_two(self):
        with (
            patch.dict(os.environ, {"AI_PROVIDERS": "openai"}, clear=False),
            patch.object(smoke, "load_env_file"),
            patch.object(smoke, "load_api_keys") as load_gemini,
            patch.object(smoke, "configured_rest_providers", return_value=[]),
        ):
            code = smoke.main()

        self.assertEqual(2, code)
        load_gemini.assert_not_called()


if __name__ == "__main__":
    unittest.main()
