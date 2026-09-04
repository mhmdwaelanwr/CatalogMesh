import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ai_product_photo_sorter import reports_cli


class ReportsCliTests(unittest.TestCase):
    def test_list_and_show_use_known_report_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "SMART_REPORT.md"
            report.write_text("# CatalogMesh\n\nOK\n", encoding="utf-8")

            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(reports_cli.main(["list", tmp, "--json"]), 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["reports"][0]["path"], "SMART_REPORT.md")

            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(reports_cli.main(["show", tmp, "SMART_REPORT.md"]), 0)
            self.assertIn("CatalogMesh", out.getvalue())

    def test_show_rejects_traversal_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "random.txt").write_text("not a registered report", encoding="utf-8")
            with self.assertRaises(SystemExit):
                reports_cli.main(["show", tmp, "../outside.txt"])
            with self.assertRaises(SystemExit):
                reports_cli.main(["show", tmp, "random.txt"])

    def test_large_or_unsupported_reads_stay_bounded_by_shared_preview_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "quality_score.txt"
            report.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
            with self.assertRaises(SystemExit):
                reports_cli.main(["show", tmp, "quality_score.txt"])


if __name__ == "__main__":
    unittest.main()
