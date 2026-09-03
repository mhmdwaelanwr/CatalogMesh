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

    def test_cli_exposes_safe_automation_commands(self):
        parser = build_parser()
        commands = parser._subparsers._group_actions[0].choices
        self.assertEqual(set(commands), {"scan", "missing-assets", "missing-local", "propose-matches", "prepare-shopify-draft", "watch"})
        self.assertNotIn("publish", commands)


if __name__ == "__main__":
    unittest.main()
