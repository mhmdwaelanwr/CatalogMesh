import csv
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ai_product_photo_sorter import rclone_autocopy


class RcloneAutoCopyTests(unittest.TestCase):
    def setUp(self):
        rclone_autocopy._COPIED_OUTPUTS.clear()
        self.env = mock.patch.dict(
            os.environ,
            {
                "PRODUCT_SORTER_RCLONE_AUTO_COPY": "true",
                "PRODUCT_SORTER_RCLONE_REMOTE": "gdrive:",
                "PRODUCT_SORTER_RCLONE_PATH": "CatalogMesh",
                "PRODUCT_SORTER_RCLONE_MODE": "sync",
                "PRODUCT_SORTER_RCLONE_TRANSFERS": "4",
                "PRODUCT_SORTER_RCLONE_CHECKERS": "8",
            },
            clear=True,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        rclone_autocopy._COPIED_OUTPUTS.clear()

    @staticmethod
    def _status(output: Path, statuses: list[str]) -> None:
        with (output / "processing_status.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=["filename", "status"])
            writer.writeheader()
            for index, status in enumerate(statuses, 1):
                writer.writerow({"filename": f"photo-{index}.jpg", "status": status})

    @mock.patch("ai_product_photo_sorter.rclone_autocopy.stream_transfer")
    def test_incomplete_operation_never_starts_remote_transfer(self, transfer):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Sorted_Products"
            output.mkdir()
            self._status(output, ["completed", "pending"])
            self.assertFalse(rclone_autocopy.auto_copy_after_success(output))
        transfer.assert_not_called()

    @mock.patch("ai_product_photo_sorter.rclone_autocopy.append_sync_audit")
    @mock.patch("ai_product_photo_sorter.rclone_autocopy.stream_transfer", return_value=0)
    def test_successful_cli_autocopy_forces_copy_and_targets_output_folder(self, transfer, audit):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Sorted_Products"
            output.mkdir()
            self._status(output, ["completed", "completed"])
            self.assertTrue(rclone_autocopy.auto_copy_after_success(output, emit=lambda _line: None))

        args, kwargs = transfer.call_args
        self.assertEqual(args[1], "gdrive:CatalogMesh/Sorted_Products")
        self.assertEqual(kwargs["options"].mode, "copy")
        self.assertFalse(kwargs["options"].dry_run)
        self.assertEqual(audit.call_args.kwargs["mode"], "copy")
        self.assertTrue(audit.call_args.kwargs["automatic"])

    @mock.patch("ai_product_photo_sorter.rclone_autocopy.stream_transfer")
    def test_desktop_process_marker_prevents_duplicate_cli_autocopy(self, transfer):
        os.environ["PRODUCT_SORTER_KEY_RESPONSE_FILE"] = "desktop-key-response.txt"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Sorted_Products"
            output.mkdir()
            self._status(output, ["completed"])
            self.assertFalse(rclone_autocopy.auto_copy_after_success(output))
        transfer.assert_not_called()

    @mock.patch("ai_product_photo_sorter.rclone_autocopy.auto_copy_after_success")
    def test_hook_triggers_only_from_real_run_completed_event(self, auto_copy):
        events = []

        def base_log(output, event, message):
            events.append((Path(output), event, message))

        module = SimpleNamespace(append_log=base_log)
        rclone_autocopy.apply_rclone_autocopy(module)
        output = Path("Sorted_Products")

        module.append_log(output, "RUN_STARTED", "start")
        auto_copy.assert_not_called()
        module.append_log(output, "RUN_COMPLETED", "done")
        auto_copy.assert_called_once_with(output, log_event=base_log)
        self.assertEqual([event for _, event, _ in events], ["RUN_STARTED", "RUN_COMPLETED"])

    @mock.patch("ai_product_photo_sorter.rclone_autocopy.append_sync_audit")
    @mock.patch("ai_product_photo_sorter.rclone_autocopy.stream_transfer", return_value=1)
    def test_failed_attempt_is_not_blindly_retried_in_same_process(self, transfer, _audit):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Sorted_Products"
            output.mkdir()
            self._status(output, ["completed"])
            self.assertFalse(rclone_autocopy.auto_copy_after_success(output, emit=lambda _line: None))
            self.assertFalse(rclone_autocopy.auto_copy_after_success(output, emit=lambda _line: None))
        self.assertEqual(transfer.call_count, 1)


if __name__ == "__main__":
    unittest.main()
