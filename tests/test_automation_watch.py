import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.watch_daemon import load_snapshot, watch_once


class AutomationWatchTests(unittest.TestCase):
    def test_watch_once_persists_and_diffs_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "shoot"
            root.mkdir()
            state = Path(directory) / "watch.json"
            first = root / "SKU1_front.jpg"
            first.write_bytes(b"first")
            initial = watch_once(root, state)
            self.assertEqual([item.path for item in initial["added"]], [str(first.resolve())])
            self.assertEqual(len(load_snapshot(state)), 1)

            second = root / "SKU2_back.png"
            second.write_bytes(b"second")
            changed = watch_once(root, state)
            self.assertEqual([item.path for item in changed["added"]], [str(second.resolve())])
            self.assertEqual(changed["removed"], [])

            first.unlink()
            removed = watch_once(root, state)
            self.assertEqual([item.path for item in removed["removed"]], [str(first.resolve())])
            self.assertEqual(list(Path(directory).glob(".watch.json.*.tmp")), [])

    def test_load_snapshot_rejects_directory_state_path(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            state.mkdir()
            with self.assertRaisesRegex(ValueError, "not a file"):
                load_snapshot(state)

    def test_load_snapshot_rejects_corrupted_asset_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "watch.json"
            state.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "assets": [{"path": "missing-fields.jpg"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "snapshot asset entry"):
                load_snapshot(state)

    def test_cli_exposes_safe_automation_commands_using_public_parse_behavior(self):
        parser = build_parser()
        samples = {
            "scan": ["scan", "shoot"],
            "missing-assets": ["missing-assets", "catalog.csv"],
            "missing-local": ["missing-local", "catalog.csv", "shoot"],
            "propose-matches": ["propose-matches", "approved.csv", "catalog.csv"],
            "open-review-queue": ["open-review-queue", "review.json"],
            "prepare-shopify-draft": ["prepare-shopify-draft", "matches.json"],
            "request-external-action": ["request-external-action", "shopify.stage_drafts", "payload.json", "request.json"],
            "approve-external-action": ["approve-external-action", "request.json", "grant.json", "--confirm", "APPROVE apr_demo"],
            "validate-approval": ["validate-approval", "request.json", "grant.json"],
            "reserve-approved-action": ["reserve-approved-action", "request.json", "grant.json", "state"],
            "record-execution-result": ["record-execution-result", "reservation.json", "audit.jsonl", "--status", "succeeded", "--attempt", "1"],
            "execute-shopify-stage": ["execute-shopify-stage", "request.json", "reservation.json"],
            "watch": ["watch", "shoot"],
        }
        for command, argv in samples.items():
            with self.subTest(command=command):
                self.assertEqual(parser.parse_args(argv).command, command)

        with self.assertRaises(SystemExit):
            parser.parse_args(["publish"])


if __name__ == "__main__":
    unittest.main()
