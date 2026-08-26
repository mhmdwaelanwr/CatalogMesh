import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_product_photo_sorter import core


class CliReportPromptTests(unittest.TestCase):
    def _argv(self, *extra: str) -> list[str]:
        return [
            "product-sorter",
            "--source", "/tmp/products",
            "--output", "/tmp/sorted",
            *extra,
        ]

    def test_interactive_cli_prompts_and_enables_report(self):
        with patch.object(sys, "argv", self._argv()), patch.dict(
            os.environ,
            {"PRODUCT_SORTER_MD_REPORT": "false", "APP_LANGUAGE": "en"},
        ), patch("builtins.input", return_value="y") as prompt:
            args = core.parse_args(Path("/tmp/no-product-sorter-env"))
            self.assertEqual(os.environ["PRODUCT_SORTER_MD_REPORT"], "true")

        self.assertTrue(args.md_report)
        prompt.assert_called_once()
        self.assertIn("smart Markdown report", prompt.call_args.args[0])

    def test_interactive_cli_uses_saved_setting_as_visible_default(self):
        with patch.object(sys, "argv", self._argv()), patch.dict(
            os.environ,
            {"PRODUCT_SORTER_MD_REPORT": "true", "APP_LANGUAGE": "en"},
        ), patch("builtins.input", return_value="") as prompt:
            args = core.parse_args(Path("/tmp/no-product-sorter-env"))

        self.assertTrue(args.md_report)
        self.assertIn("[Y/n]", prompt.call_args.args[0])

    def test_explicit_flag_skips_interactive_question(self):
        with patch.object(sys, "argv", self._argv("--md-report")), patch.dict(
            os.environ,
            {"PRODUCT_SORTER_MD_REPORT": "false", "APP_LANGUAGE": "en"},
        ), patch("builtins.input") as prompt:
            args = core.parse_args(Path("/tmp/no-product-sorter-env"))

        self.assertTrue(args.md_report)
        prompt.assert_not_called()

    def test_non_interactive_cli_skips_question_and_uses_configuration(self):
        with patch.object(sys, "argv", self._argv("--non-interactive")), patch.dict(
            os.environ,
            {"PRODUCT_SORTER_MD_REPORT": "true", "APP_LANGUAGE": "en"},
        ), patch("builtins.input") as prompt:
            args = core.parse_args(Path("/tmp/no-product-sorter-env"))

        self.assertTrue(args.md_report)
        prompt.assert_not_called()

    def test_arabic_yes_is_accepted(self):
        with patch.object(sys, "argv", self._argv()), patch.dict(
            os.environ,
            {"PRODUCT_SORTER_MD_REPORT": "false", "APP_LANGUAGE": "ar"},
        ), patch("builtins.input", return_value="نعم"):
            args = core.parse_args(Path("/tmp/no-product-sorter-env"))

        self.assertTrue(args.md_report)


if __name__ == "__main__":
    unittest.main()
