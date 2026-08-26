import csv
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ai_product_photo_sorter import core
from ai_product_photo_sorter import gui
from ai_product_photo_sorter.smart_report import REPORT_NAME, generate_smart_report


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class SmartReportTests(unittest.TestCase):
    def _fixture(self, root: Path):
        source = root / "source.jpg"
        source.write_bytes(b"photo-data")
        output = root / "Sorted_Products"
        output.mkdir()
        with (output / "classification_report.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "filename", "product_group", "category", "view", "brand",
                    "model", "catalog_match", "confidence", "status", "reason",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "filename": "source.jpg",
                    "product_group": "Product_0001_Brand_Model",
                    "category": "usb_hub",
                    "view": "front",
                    "brand": "Brand",
                    "model": "Model",
                    "catalog_match": "",
                    "confidence": "0.94",
                    "status": "classified",
                    "reason": "visible packaging",
                }
            )
        with (output / "processing_status.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=["filename", "status"])
            writer.writeheader()
            writer.writerow({"filename": "source.jpg", "status": "completed"})
        items = [
            {
                "path": source,
                "taken_at": datetime(2026, 8, 26, 10, 0, 0),
                "category": "usb_hub",
                "confidence": 0.94,
            }
        ]
        return output, items

    def test_operation_report_is_one_comprehensive_markdown_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output, items = self._fixture(Path(directory))

            def fake_ai(_facts, _language):
                return (
                    {
                        "executive_summary": "Catalog quality is strong.",
                        "observations": ["One USB hub product group was identified."],
                        "recommendations": ["Keep category naming consistent."],
                        "store_actions": ["Review the final listing before publishing."],
                        "caveats": ["AI advice is advisory."],
                    },
                    None,
                )

            with patch.dict(os.environ, {"APP_LANGUAGE": "en"}):
                path = generate_smart_report(items, output, 0.75, fake_ai)

            text = path.read_text(encoding="utf-8")
            self.assertEqual(path.name, REPORT_NAME)
            self.assertIn("Operation snapshot", text)
            self.assertIn("Discovered taxonomy", text)
            self.assertIn("Product inventory", text)
            self.assertIn("Review queue", text)
            self.assertIn("Operation file architecture", text)
            self.assertIn("usb_hub", text)
            self.assertIn("Product_0001_Brand_Model", text)
            self.assertEqual([p.name for p in output.glob("*.md")], [REPORT_NAME])

    def test_ai_failure_does_not_prevent_programmatic_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output, items = self._fixture(Path(directory))

            def broken_ai(_facts, _language):
                raise RuntimeError("provider unavailable")

            with patch.dict(os.environ, {"APP_LANGUAGE": "en"}):
                path = generate_smart_report(items, output, 0.75, broken_ai)

            text = path.read_text(encoding="utf-8")
            self.assertTrue(path.is_file())
            self.assertIn("AI narrative was unavailable", text)
            self.assertIn("Photos classified", text)
            self.assertIn("usb_hub", text)

    def test_cli_md_report_flag_is_consumed_by_shared_parser(self):
        argv = [
            "product-sorter",
            "--source", "/tmp/products",
            "--output", "/tmp/sorted",
            "--md-report",
        ]
        with patch.object(sys, "argv", argv), patch.dict(
            os.environ,
            {"PRODUCT_SOURCE": "", "PRODUCT_OUTPUT": "", "PRODUCT_SORTER_MD_REPORT": "false"},
        ):
            args = core.parse_args(Path("/tmp/no-product-sorter-env"))
            self.assertTrue(args.md_report)
            self.assertEqual(os.environ["PRODUCT_SORTER_MD_REPORT"], "true")

    def test_gui_command_passes_md_report_flag_only_when_checked(self):
        class Dummy:
            vars = {
                "source": _Value("/photos"),
                "output": _Value("/sorted"),
                "prices": _Value(""),
                "sample": _Value(""),
                "md_report": _Value(True),
            }

        command = gui._impl.App.command(Dummy())
        self.assertIn("--md-report", command)

        Dummy.vars["md_report"] = _Value(False)
        command = gui._impl.App.command(Dummy())
        self.assertNotIn("--md-report", command)


if __name__ == "__main__":
    unittest.main()
