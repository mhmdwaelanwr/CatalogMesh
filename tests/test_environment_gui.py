import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_product_photo_sorter.environment_gui import _mask_value, _validate_setting
from ai_product_photo_sorter import setup_wizard


class EnvironmentGuiTests(unittest.TestCase):
    def test_sensitive_values_are_masked(self):
        self.assertEqual("••••••••", _mask_value("GEMINI_API_KEY_1", "secret"))
        self.assertEqual("gemini", _mask_value("AI_PROVIDERS", "gemini"))
        self.assertEqual("", _mask_value("GEMINI_API_KEY_1", ""))

    def test_provider_typo_is_canonicalized(self):
        self.assertEqual("gemini,openai", _validate_setting("AI_PROVIDERS", "gemeni,OpenAI"))

    def test_numeric_and_boolean_settings_are_validated(self):
        self.assertEqual("8", _validate_setting("BATCH_SIZE", "8"))
        self.assertEqual("0.75", _validate_setting("CONFIDENCE", "0.75"))
        self.assertEqual("true", _validate_setting("VALIDATE_KEYS", "yes"))
        self.assertEqual("false", _validate_setting("PRODUCT_SORTER_MD_REPORT", "0"))
        with self.assertRaises(ValueError):
            _validate_setting("BATCH_SIZE", "9")
        with self.assertRaises(ValueError):
            _validate_setting("CONFIDENCE", "1.2")
        with self.assertRaises(ValueError):
            _validate_setting("BENCHMARK_LIMIT", "0")

    def test_output_mode_is_restricted_to_supported_values(self):
        self.assertEqual("hardlink", _validate_setting("PRODUCT_SORTER_OUTPUT_MODE", "HARDLINK"))
        with self.assertRaises(ValueError):
            _validate_setting("PRODUCT_SORTER_OUTPUT_MODE", "move")

    def test_desktop_settings_are_persisted_by_env_writer(self):
        text = setup_wizard.build_env_text(
            {
                "AI_PROVIDERS": "gemini",
                "APP_THEME": "dark",
                "PRODUCT_SORTER_MD_REPORT": "true",
                "BENCHMARK_LIMIT": "50",
                "PRODUCT_SORTER_OUTPUT_MODE": "copy",
                "SHOPIFY_STORE_DOMAIN": "demo.myshopify.com",
                "SHOPIFY_API_VERSION": "2026-07",
                "SHOPIFY_PUBLICATION_ID": "gid://shopify/Publication/123",
            }
        )
        self.assertIn("APP_THEME=dark", text)
        self.assertIn("PRODUCT_SORTER_MD_REPORT=true", text)
        self.assertIn("BENCHMARK_LIMIT=50", text)
        self.assertIn("PRODUCT_SORTER_OUTPUT_MODE=copy", text)
        self.assertIn("SHOPIFY_STORE_DOMAIN=demo.myshopify.com", text)
        self.assertIn("SHOPIFY_API_VERSION=2026-07", text)
        self.assertIn("SHOPIFY_PUBLICATION_ID=gid://shopify/Publication/123", text)
        self.assertNotIn("SHOPIFY_ADMIN_ACCESS_TOKEN", text)

    def test_shopify_token_is_keyring_only_even_when_legacy_switch_is_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            values = {
                "AI_PROVIDERS": "gemini",
                "USE_KEYRING": "false",
                "SHOPIFY_STORE_DOMAIN": "demo.myshopify.com",
                "SHOPIFY_API_VERSION": "2026-07",
                "SHOPIFY_ADMIN_ACCESS_TOKEN": "shpat_mock_secret",
            }
            with patch("ai_product_photo_sorter.setup_wizard.save_secrets", return_value=True) as save:
                setup_wizard.save_env(values, path)
            save.assert_called_once_with({"SHOPIFY_ADMIN_ACCESS_TOKEN": "shpat_mock_secret"})
            text = path.read_text(encoding="utf-8")
            self.assertIn("SHOPIFY_STORE_DOMAIN=demo.myshopify.com", text)
            self.assertNotIn("shpat_mock_secret", text)
            self.assertNotIn("SHOPIFY_ADMIN_ACCESS_TOKEN", text)

    def test_shopify_token_save_fails_closed_when_keyring_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            with patch("ai_product_photo_sorter.setup_wizard.save_secrets", return_value=False):
                with self.assertRaisesRegex(ValueError, "OS keyring"):
                    setup_wizard.save_env(
                        {
                            "USE_KEYRING": "false",
                            "SHOPIFY_ADMIN_ACCESS_TOKEN": "shpat_mock_secret",
                        },
                        path,
                    )
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
