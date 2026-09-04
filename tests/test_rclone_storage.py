import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ai_product_photo_sorter.rclone_storage import (
    RcloneError,
    TransferOptions,
    append_sync_audit,
    build_transfer_command,
    list_remotes,
    normalize_remote_name,
    remote_target,
    stream_transfer,
)


class RcloneStorageTests(unittest.TestCase):
    def test_remote_target_uses_separate_validated_remote_and_path(self):
        self.assertEqual(remote_target("gdrive", "CatalogMesh/Run 1"), "gdrive:CatalogMesh/Run 1")
        self.assertEqual(normalize_remote_name("gdrive"), "gdrive:")
        with self.assertRaises(ValueError):
            remote_target("bad/name", "CatalogMesh")
        with self.assertRaises(ValueError):
            remote_target("gdrive", "../outside")

    def test_copy_is_default_and_does_not_include_delete_flags(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ai_product_photo_sorter.rclone_storage.resolve_rclone_binary",
            return_value="/usr/bin/rclone",
        ):
            command = build_transfer_command(Path(tmp), "gdrive:CatalogMesh/Run")
        self.assertEqual(command[1], "copy")
        self.assertNotIn("--delete-before", command)
        self.assertNotIn("--delete-during", command)
        self.assertNotIn("--delete-after", command)
        self.assertIn(".product_sorter.lock", command)
        self.assertIn("*.tmp", command)

    def test_sync_requires_explicit_mode_and_dry_run_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ai_product_photo_sorter.rclone_storage.resolve_rclone_binary",
            return_value="rclone",
        ):
            command = build_transfer_command(
                tmp,
                "onedrive:CatalogMesh/Run",
                options=TransferOptions(mode="sync", dry_run=True, transfers=2, checkers=3, bwlimit="10M"),
            )
        self.assertEqual(command[1], "sync")
        self.assertIn("--dry-run", command)
        self.assertIn("--bwlimit", command)
        self.assertIn("10M", command)

    def test_transfer_options_fail_closed_on_invalid_parallelism_or_mode(self):
        with self.assertRaises(ValueError):
            TransferOptions(mode="move").validated()
        with self.assertRaises(ValueError):
            TransferOptions(transfers=0).validated()
        with self.assertRaises(ValueError):
            TransferOptions(checkers=100).validated()
        with self.assertRaises(ValueError):
            TransferOptions(bwlimit="10M;rm -rf /").validated()

    def test_list_remotes_filters_unexpected_output(self):
        with patch(
            "ai_product_photo_sorter.rclone_storage.resolve_rclone_binary",
            return_value="rclone",
        ), patch(
            "ai_product_photo_sorter.rclone_storage._capture",
            return_value="gdrive:\nOne Drive:\n../../bad:\n",
        ):
            self.assertEqual(list_remotes(), ("gdrive:", "One Drive:"))

    def test_stream_transfer_uses_argv_and_shell_false(self):
        process = MagicMock()
        process.stdout = iter(["Transferred: 1 / 1\n"])
        process.wait.return_value = 0
        with tempfile.TemporaryDirectory() as tmp, patch(
            "ai_product_photo_sorter.rclone_storage.resolve_rclone_binary",
            return_value="rclone",
        ), patch(
            "ai_product_photo_sorter.rclone_storage.subprocess.Popen",
            return_value=process,
        ) as popen:
            lines = []
            code = stream_transfer(tmp, "gdrive:CatalogMesh/Run", on_line=lines.append)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["Transferred: 1 / 1"])
        args, kwargs = popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertFalse(kwargs["shell"])

    def test_audit_is_local_and_credential_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = append_sync_audit(
                tmp,
                target="gdrive:CatalogMesh/Run",
                mode="copy",
                dry_run=False,
                returncode=0,
                automatic=True,
            )
            record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["target"], "gdrive:CatalogMesh/Run")
        self.assertTrue(record["automatic"])
        serialized = json.dumps(record).lower()
        self.assertNotIn("password", serialized)
        self.assertNotIn("token", serialized)
        self.assertNotIn("secret", serialized)

    def test_missing_rclone_error_is_clear(self):
        with patch("ai_product_photo_sorter.rclone_storage.shutil.which", return_value=None), patch.dict(
            "os.environ", {}, clear=True
        ):
            from ai_product_photo_sorter.rclone_storage import resolve_rclone_binary
            with self.assertRaises(RcloneError):
                resolve_rclone_binary()


if __name__ == "__main__":
    unittest.main()
