import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ai_product_photo_sorter import automation_cli


class StorageCliTests(unittest.TestCase):
    def test_storage_commands_exist(self):
        parser = automation_cli.build_parser()
        choices = set()
        for action in parser._actions:
            if isinstance(getattr(action, "choices", None), dict):
                choices.update(action.choices)
        self.assertTrue({"storage-version","storage-remotes","storage-test","storage-dry-run","storage-copy","storage-sync"}.issubset(choices))

    def test_sync_requires_explicit_confirmation_flag(self):
        parser = automation_cli.build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                parser.parse_args(["storage-sync", tmp, "gdrive:"])

    @mock.patch("ai_product_photo_sorter.automation_cli.rclone_version", return_value="rclone v1.71.0")
    def test_version_emits_json(self, _version):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(automation_cli.main(["storage-version"]), 0)
        self.assertEqual(json.loads(out.getvalue())["version"], "rclone v1.71.0")

    @mock.patch("ai_product_photo_sorter.automation_cli.build_transfer_command", return_value=["rclone", "sync"])
    @mock.patch("ai_product_photo_sorter.automation_cli.run_transfer", return_value="ok")
    def test_sync_uses_shared_backend(self, run, build):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(automation_cli.main(["storage-sync", tmp, "gdrive:", "--remote-path", "Catalog", "--confirm-sync"]), 0)
        self.assertEqual(json.loads(out.getvalue())["mode"], "sync")
        self.assertEqual(run.call_args.args[1], "gdrive:Catalog")
        self.assertEqual(run.call_args.kwargs["options"].mode, "sync")
        self.assertEqual(build.call_args.args[1], "gdrive:Catalog")


if __name__ == "__main__":
    unittest.main()
