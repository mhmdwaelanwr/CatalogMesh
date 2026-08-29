from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "generate_mock_product_benchmark.py"


class MockProductBenchmarkTests(unittest.TestCase):
    def test_generator_creates_labeled_mock_evidence_calibration_and_routing_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "mock"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertIn("not valid for production", result.stdout.lower())
            self.assertIn("routing simulation", result.stdout.lower())

            photos = sorted((output / "photos").glob("*.jpg"))
            self.assertEqual(len(photos), 48)

            with (output / "ground_truth.csv").open(encoding="utf-8-sig", newline="") as handle:
                ground_truth = list(csv.DictReader(handle))
            self.assertEqual(len(ground_truth), 48)
            self.assertEqual(len({row["product_group"] for row in ground_truth}), 8)
            self.assertTrue(all(row["product_group"] for row in ground_truth))

            with (output / "hybrid_embedding_shadow.csv").open(encoding="utf-8-sig", newline="") as handle:
                shadow = list(csv.DictReader(handle))
            self.assertEqual(len(shadow), 47)
            self.assertIn("same", {row["ground_truth_relation"] for row in shadow})
            self.assertIn("different", {row["ground_truth_relation"] for row in shadow})

            summary = json.loads((output / "mock_benchmark_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["schema_version"], 2)
            self.assertEqual(summary["dataset_type"], "synthetic_mock")
            self.assertFalse(summary["production_evidence"])

            calibration = summary["calibration"]
            self.assertFalse(calibration["routing_enabled"])
            self.assertTrue(calibration["recommendation_available"])
            self.assertTrue(calibration["promotion_ready"])
            self.assertGreater(calibration["same_threshold"], calibration["different_threshold"])
            self.assertGreaterEqual(calibration["same_precision"], 0.98)
            self.assertGreaterEqual(calibration["different_precision"], 0.98)
            self.assertGreater(calibration["ambiguous_boundaries"], 0)

            routing = summary["routing_simulation"]
            self.assertEqual(routing["mode"], "simulation")
            self.assertFalse(routing["production_routing_enabled"])
            self.assertEqual(routing["actual_provider_calls_skipped"], 0)
            self.assertGreater(routing["local_routed_boundaries"], 0)
            self.assertGreater(routing["vision_boundaries_remaining"], 0)
            self.assertGreater(routing["local_routing_coverage"], 0.0)
            self.assertLess(routing["local_routing_coverage"], 1.0)
            self.assertEqual(routing["unsafe_local_misroutes"], 0)
            self.assertEqual(routing["local_routing_accuracy"], 1.0)

            self.assertTrue((output / "calibration" / "hybrid_threshold_calibration.json").is_file())
            self.assertTrue((output / "calibration" / "HYBRID_THRESHOLD_CALIBRATION.md").is_file())
            self.assertTrue((output / "routing-lab" / "hybrid_routing_simulation.json").is_file())
            self.assertTrue((output / "routing-lab" / "HYBRID_ROUTING_SIMULATION.md").is_file())
            self.assertTrue((output / "routing-lab" / "hybrid_routing_simulation.csv").is_file())


if __name__ == "__main__":
    unittest.main()
