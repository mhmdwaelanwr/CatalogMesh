import json
import tempfile
import time
import unittest
from pathlib import Path

from ai_product_photo_sorter.benchmark import (
    BatchMetric,
    BenchmarkSession,
    build_result,
    hardware_snapshot,
    render_markdown,
    write_reports,
)


class BenchmarkTests(unittest.TestCase):
    def test_hardware_snapshot_is_safe_and_structured(self):
        snapshot = hardware_snapshot()
        self.assertIn("platform", snapshot)
        self.assertIn("python", snapshot)
        self.assertIn("logical_cpus", snapshot)
        self.assertIn("gpu", snapshot)

    def test_result_and_markdown_use_real_status_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "photos"
            output = root / "out" / "benchmarks" / "run_test"
            source.mkdir(parents=True)
            output.mkdir(parents=True)
            (source / "a.jpg").write_bytes(b"a" * 20)
            (source / "b.jpg").write_bytes(b"b" * 30)
            (output / "processing_status.csv").write_text(
                "position,filename,taken_at,status\n"
                "1,a.jpg,2026-01-01 00:00:00,completed\n"
                "2,b.jpg,2026-01-01 00:00:01,completed\n",
                encoding="utf-8-sig",
            )
            (output / "api_usage.csv").write_text(
                "provider,model,input_tokens,output_tokens,estimated_cost,created_at\n"
                "gemini,test-model,100,25,0.01,2026-01-01\n",
                encoding="utf-8-sig",
            )
            session = BenchmarkSession(
                source=source,
                base_output=root / "out",
                run_output=output,
                hardware_start={
                    "platform": "test",
                    "python": "3.x",
                    "machine": "test",
                    "processor": "test",
                    "logical_cpus": 4,
                    "gpu": [],
                },
            )
            session.started_monotonic = time.perf_counter() - 2
            session.batches.append(
                BatchMetric("gemini", "test-model", 2, 1.5, True, 100, 25)
            )
            session.encoded_images = 2
            session.encoded_bytes = 500
            session.encode_seconds = 0.2
            session.return_code = 0

            result = build_result(session)
            self.assertEqual(result["photos_selected"], 2)
            self.assertEqual(result["photos_completed"], 2)
            self.assertEqual(result["source_bytes"], 50)
            self.assertEqual(result["logical_provider_calls"], 1)
            self.assertEqual(result["input_tokens"], 100)
            self.assertEqual(result["output_tokens"], 25)
            self.assertAlmostEqual(result["estimated_cost"], 0.01)

            markdown = render_markdown(result)
            self.assertIn("Product Sorter Benchmark Report", markdown)
            self.assertIn("test-model", markdown)
            self.assertIn("Logical provider calls", markdown)

    def test_write_reports_creates_markdown_json_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "photos"
            output = root / "out" / "benchmarks" / "run_test"
            source.mkdir(parents=True)
            output.mkdir(parents=True)
            (output / "processing_status.csv").write_text(
                "position,filename,taken_at,status\n", encoding="utf-8-sig"
            )
            session = BenchmarkSession(
                source=source,
                base_output=root / "out",
                run_output=output,
                hardware_start=hardware_snapshot(),
            )
            session.return_code = 0
            md_path, json_path, _ = write_reports(session)
            self.assertTrue(md_path.is_file())
            self.assertTrue(json_path.is_file())
            self.assertTrue((output.parent / "history.jsonl").is_file())
            self.assertTrue((output.parent / "latest.txt").is_file())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
