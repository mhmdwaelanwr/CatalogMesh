import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ai_product_photo_sorter import automation_cli, storage_cli


class StorageCliTests(unittest.TestCase):
    def test_first_class_storage_commands_exist(self):
        parser = storage_cli.build_parser()
        choices = set()
        for action in parser._actions:
            if isinstance(getattr(action, "choices", None), dict):
                choices.update(action.choices)
        self.assertEqual(
            choices,
            {"version", "remotes", "test", "dry-run", "copy", "sync"},
        )

    def test_first_class_target_validation_rejects_traversal(self):
        self.assertEqual(
            storage_cli.validate_remote_target("gdrive:/CatalogMesh//Run"),
            "gdrive:CatalogMesh/Run",
        )
        with self.assertRaises(ValueError):
            storage_cli.validate_remote_target("gdrive:CatalogMesh/../outside")

    @mock.patch(
        "ai_product_photo_sorter.storage_cli.rclone_version",
        return_value="rclone v1.71.0",
    )
    def test_version_is_human_readable_by_default_and_json_is_optional(self, _version):
        human = io.StringIO()
        with redirect_stdout(human):
            self.assertEqual(storage_cli.main(["version"]), 0)
        self.assertEqual(human.getvalue().strip(), "rclone v1.71.0")

        machine = io.StringIO()
        with redirect_stdout(machine):
            self.assertEqual(storage_cli.main(["version", "--json"]), 0)
        self.assertEqual(json.loads(machine.getvalue())["version"], "rclone v1.71.0")

    @mock.patch("ai_product_photo_sorter.storage_cli.stream_transfer", return_value=0)
    @mock.patch(
        "ai_product_photo_sorter.storage_cli.build_transfer_command",
        return_value=["rclone", "sync"],
    )
    @mock.patch("ai_product_photo_sorter.storage_cli.append_sync_audit")
    def test_first_class_sync_requires_exact_full_target_confirmation(
        self, _audit, _build, stream
    ):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                storage_cli.main(
                    [
                        "sync",
                        tmp,
                        "gdrive:CatalogMesh/Outputs",
                        "--confirm",
                        "SYNC gdrive:",
                    ]
                )
            self.assertIn("SYNC gdrive:CatalogMesh/Outputs", str(ctx.exception))
            stream.assert_not_called()

            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    storage_cli.main(
                        [
                            "sync",
                            tmp,
                            "gdrive:CatalogMesh/Outputs",
                            "--confirm",
                            "SYNC gdrive:CatalogMesh/Outputs",
                            "--json",
                        ]
                    ),
                    0,
                )
        self.assertEqual(stream.call_args.args[1], "gdrive:CatalogMesh/Outputs")
        self.assertEqual(stream.call_args.kwargs["options"].mode, "sync")
        self.assertEqual(json.loads(out.getvalue())["target"], "gdrive:CatalogMesh/Outputs")

    @mock.patch(
        "ai_product_photo_sorter.automation_cli.build_transfer_command",
        return_value=["rclone", "sync"],
    )
    @mock.patch("ai_product_photo_sorter.automation_cli.run_transfer", return_value="ok")
    def test_automation_storage_sync_keeps_exact_typed_confirmation(self, run, build):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                automation_cli.main(
                    [
                        "storage-sync",
                        tmp,
                        "gdrive:",
                        "--remote-path",
                        "Catalog",
                        "--confirm-sync",
                        "SYNC gdrive:",
                    ]
                )
            self.assertIn("SYNC gdrive:Catalog", str(ctx.exception))
            run.assert_not_called()

            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    automation_cli.main(
                        [
                            "storage-sync",
                            tmp,
                            "gdrive:",
                            "--remote-path",
                            "Catalog",
                            "--confirm-sync",
                            "SYNC gdrive:Catalog",
                        ]
                    ),
                    0,
                )
        self.assertEqual(json.loads(out.getvalue())["mode"], "sync")
        self.assertEqual(run.call_args.args[1], "gdrive:Catalog")
        self.assertEqual(build.call_args.args[1], "gdrive:Catalog")


if __name__ == "__main__":
    unittest.main()
