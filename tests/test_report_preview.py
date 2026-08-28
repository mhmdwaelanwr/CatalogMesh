import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.report_preview import (
    discover_reports,
    markdown_blocks,
    read_report_text,
    report_kind,
)


class ReportPreviewTests(unittest.TestCase):
    def test_markdown_parser_covers_product_sorter_report_shapes(self):
        blocks = markdown_blocks(
            "# Benchmark\n\n> Generated now\n\n"
            "## Summary\n\n| Metric | Value |\n| --- | ---: |\n| Photos | 50 |\n\n"
            "- First note\n\n```json\n{\"ok\": true}\n```\n"
        )
        kinds = [block["kind"] for block in blocks]
        self.assertIn("heading", kinds)
        self.assertIn("quote", kinds)
        self.assertIn("table", kinds)
        self.assertIn("table_separator", kinds)
        self.assertIn("bullet", kinds)
        self.assertIn("code", kinds)
        self.assertEqual("Benchmark", blocks[0]["text"])

    def test_discovery_avoids_recursive_photo_tree_and_finds_benchmarks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            smart = root / "SMART_REPORT.md"
            smart.write_text("# Smart", encoding="utf-8")
            run = root / "benchmarks" / "run_1"
            run.mkdir(parents=True)
            benchmark = run / "BENCHMARK_REPORT.md"
            benchmark.write_text("# Benchmark", encoding="utf-8")
            (run / "benchmark.json").write_text("{}", encoding="utf-8")
            photo_dir = root / "mouse" / "Product_0001"
            photo_dir.mkdir(parents=True)
            (photo_dir / "not_a_report.md").write_text("ignore", encoding="utf-8")

            reports = discover_reports(root)
            self.assertIn(smart, reports)
            self.assertIn(benchmark, reports)
            self.assertIn(run / "benchmark.json", reports)
            self.assertNotIn(photo_dir / "not_a_report.md", reports)

    def test_report_reader_and_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BENCHMARK_REPORT.md"
            path.write_text("# Report", encoding="utf-8")
            self.assertEqual("# Report", read_report_text(path))
            self.assertEqual("Markdown", report_kind(path))
            self.assertEqual("CSV", report_kind(Path("status.csv")))


if __name__ == "__main__":
    unittest.main()
