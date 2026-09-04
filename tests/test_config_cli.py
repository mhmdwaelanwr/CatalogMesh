import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ai_product_photo_sorter import config_cli


class ConfigCliTests(unittest.TestCase):
    def test_commands_are_bounded_and_no_generic_executor_exists(self):
        parser = config_cli.build_parser()
        commands = set()
        for action in parser._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                commands.update(choices)
        self.assertEqual(
            commands,
            {"list", "get", "set", "set-secret", "unset", "clear-api-keys", "delete"},
        )
        self.assertNotIn("exec", commands)
        self.assertNotIn("shell", commands)

    @mock.patch("ai_product_photo_sorter.config_cli._read", return_value={"APP_THEME": "dark", "GEMINI_API_KEY_1": "secret"})
    def test_list_masks_secrets(self, _read):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(config_cli.main(["list", "--json"]), 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["settings"]["APP_THEME"], "dark")
        self.assertEqual(payload["settings"]["GEMINI_API_KEY_1"], "••••••••")
        self.assertNotIn("secret", out.getvalue())

    @mock.patch("ai_product_photo_sorter.config_cli._write")
    @mock.patch("ai_product_photo_sorter.config_cli._read", return_value={})
    def test_set_uses_same_environment_validation(self, _read, write):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(config_cli.main(["set", "APP_THEME", "light"]), 0)
        self.assertEqual(write.call_args.args[0]["APP_THEME"], "light")
        with self.assertRaises(SystemExit):
            config_cli.main(["set", "APP_THEME", "gradient"])

    @mock.patch("ai_product_photo_sorter.config_cli._write")
    @mock.patch("ai_product_photo_sorter.config_cli._read", return_value={})
    def test_secret_cannot_be_passed_in_argv(self, _read, write):
        with self.assertRaises(SystemExit):
            config_cli.main(["set", "GEMINI_API_KEY_1", "do-not-accept-this"])
        write.assert_not_called()

    @mock.patch("ai_product_photo_sorter.config_cli._write")
    @mock.patch("ai_product_photo_sorter.config_cli._read", return_value={})
    @mock.patch("ai_product_photo_sorter.config_cli.getpass.getpass", return_value="hidden-key")
    def test_set_secret_uses_hidden_prompt(self, prompt, _read, write):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(config_cli.main(["set-secret", "GEMINI_API_KEY_1"]), 0)
        prompt.assert_called_once()
        self.assertEqual(write.call_args.args[0]["GEMINI_API_KEY_1"], "hidden-key")
        self.assertNotIn("hidden-key", out.getvalue())

    @mock.patch("ai_product_photo_sorter.config_cli._write")
    @mock.patch("ai_product_photo_sorter.config_cli.clear_keyring")
    @mock.patch("ai_product_photo_sorter.config_cli._read", return_value={"GEMINI_API_KEY_1": "secret"})
    def test_clear_all_keys_requires_exact_confirmation(self, _read, clear, write):
        with self.assertRaises(SystemExit):
            config_cli.main(["clear-api-keys", "--confirm", "yes"])
        write.assert_not_called()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                config_cli.main(["clear-api-keys", "--confirm", "CLEAR API KEYS"]),
                0,
            )
        clear.assert_called_once()
        self.assertEqual(write.call_args.args[0]["GEMINI_API_KEY_1"], "")

    @mock.patch("ai_product_photo_sorter.config_cli.clear_keyring")
    @mock.patch("ai_product_photo_sorter.config_cli._path", return_value=Path("/tmp/catalogmesh-test.env"))
    def test_delete_requires_target_specific_confirmation(self, path, clear):
        with self.assertRaises(SystemExit):
            config_cli.main(["delete", "--confirm", "DELETE CONFIG"])
        with mock.patch.object(Path, "unlink") as unlink:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    config_cli.main([
                        "delete",
                        "--confirm",
                        "DELETE CONFIG /tmp/catalogmesh-test.env",
                    ]),
                    0,
                )
            unlink.assert_called_once_with(missing_ok=True)
        clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
