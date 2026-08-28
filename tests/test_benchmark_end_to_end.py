import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

# Importing the public facade applies every production extension to _core_impl.
from ai_product_photo_sorter import core as _public_core  # noqa: F401
from ai_product_photo_sorter import _core_impl as engine


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.last_usage = {}

    def generate(self, prompt, photos, image_bytes):
        self.calls += 1
        for photo in photos:
            payload = image_bytes(photo.path)
            if not payload:
                raise AssertionError("benchmark image encoding returned no payload")
        self.last_usage = {"input_tokens": 321, "output_tokens": 42}
        return json.dumps(
            {
                "items": [
                    {
                        "filename": photo.path.name,
                        "same_product_as_previous": index > 0,
                        "category": "mouse",
                        "view": "front" if index == 0 else "back",
                        "brand": "Demo",
                        "model": "M1",
                        "catalog_match": "",
                        "confidence": 0.99,
                        "reason": "synthetic benchmark",
                    }
                    for index, photo in enumerate(photos)
                ]
            }
        )


class FakePool:
    name = "openai"
    model = "fake-vision"

    def __init__(self):
        self._client = FakeClient()
        self.clients = [self._client]
        self.index = 0
        self.last_usage = {}

    @property
    def client(self):
        return self._client


class BenchmarkEndToEndTests(unittest.TestCase):
    def test_real_pipeline_benchmark_is_isolated_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Products"
            base_output = root / "Sorted_Products"
            source.mkdir()
            for index in range(3):
                Image.new("RGB", (32, 32), (index * 40, 20, 10)).save(
                    source / f"product_{index}.jpg"
                )

            pool = FakePool()

            def fake_internet(output):
                engine.append_log(
                    output,
                    "INTERNET_CHECK",
                    "quality=excellent; latency_ms=12.5",
                )
                return True

            argv = [
                "product-sorter",
                "--env-file",
                str(root / "missing.env"),
                "--source",
                str(source),
                "--output",
                str(base_output),
                "--model",
                "benchmark-test-model",
                "--batch-size",
                "3",
                "--limit",
                "3",
                "--benchmark",
                "--benchmark-label",
                "synthetic-ci",
            ]
            env = {
                "AI_PROVIDERS": "openai",
                "VALIDATE_KEYS": "false",
                "OPENAI_INPUT_COST_PER_MILLION": "1.0",
                "OPENAI_OUTPUT_COST_PER_MILLION": "2.0",
            }

            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(engine, "configured_rest_providers", return_value=[pool]),
                patch.object(engine, "ensure_requirements", return_value=True),
                patch.object(engine, "require_internet", side_effect=fake_internet),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                for _ in range(2):
                    with patch.object(sys, "argv", list(argv)):
                        self.assertEqual(engine.main(), 0)

            runs = sorted((base_output / "benchmarks").glob("run_*"))
            self.assertEqual(len(runs), 2)
            self.assertEqual(pool.client.calls, 2)
            self.assertFalse((base_output / "progress.sqlite3").exists())

            for original in source.glob("*.jpg"):
                self.assertTrue(original.is_file())

            for run in runs:
                payload = json.loads((run / "benchmark.json").read_text(encoding="utf-8"))
                self.assertEqual(payload["schema_version"], 1)
                self.assertEqual(payload["label"], "synthetic-ci")
                self.assertEqual(payload["photos_selected"], 3)
                self.assertEqual(payload["photos_completed"], 3)
                self.assertEqual(payload["logical_provider_calls"], 1)
                self.assertEqual(payload["failed_provider_calls"], 0)
                self.assertEqual(payload["image_encode_calls"], 3)
                self.assertEqual(payload["input_tokens"], 321)
                self.assertEqual(payload["output_tokens"], 42)
                self.assertGreater(payload["source_bytes"], 0)
                self.assertTrue((run / "classification_report.csv").is_file())
                self.assertTrue((run / "category_registry.json").is_file())

                config = payload["benchmark_config"]
                self.assertEqual(config["product_sorter_version"], engine.VERSION)
                self.assertEqual(config["provider_priority"], ["openai"])
                self.assertEqual(config["requested_model"], "benchmark-test-model")
                self.assertEqual(config["batch_size"], 3)
                self.assertEqual(config["photo_limit"], 3)
                self.assertFalse(config["key_validation_enabled"])

                network = payload["network_latency_ms"]
                self.assertEqual(network["sample_count"], 1)
                self.assertAlmostEqual(network["average"], 12.5)
                self.assertAlmostEqual(network["median"], 12.5)

                report = (run / "BENCHMARK_REPORT.md").read_text(encoding="utf-8")
                self.assertIn("## Reproducibility", report)
                self.assertIn("Connectivity probe latency", report)
                self.assertIn("fake-vision", report)

            history = (base_output / "benchmarks" / "history.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(history), 2)
            self.assertTrue(all(json.loads(line)["schema_version"] == 1 for line in history))
            latest = Path(
                (base_output / "benchmarks" / "latest.txt").read_text(encoding="utf-8").strip()
            )
            # macOS aliases /var to /private/var; resolve both before comparing.
            self.assertEqual(latest.parent.resolve(), runs[-1].resolve())
            self.assertTrue(latest.is_file())


if __name__ == "__main__":
    unittest.main()
