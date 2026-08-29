from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.hybrid_routing_lab import simulate_from_files, simulate_routing


ROOT = Path(__file__).resolve().parent.parent


def _write_shadow(path: Path, rows: list[tuple[str, str, float, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "previous_filename",
                "filename",
                "cosine_similarity",
                "ground_truth_relation",
            ],
        )
        writer.writeheader()
        for previous, current, similarity, truth in rows:
            writer.writerow(
                {
                    "previous_filename": previous,
                    "filename": current,
                    "cosine_similarity": f"{similarity:.8f}",
                    "ground_truth_relation": truth,
                }
            )


def _write_calibration(path: Path, *, same: float = 0.90, different: float = 0.30) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "recommendation_available": True,
                "routing_enabled": False,
                "same_threshold": same,
                "different_threshold": different,
            }
        ),
        encoding="utf-8",
    )


class HybridRoutingLabTests(unittest.TestCase):
    def test_simulation_routes_confident_boundaries_and_keeps_ambiguity_on_vision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shadow = root / "shadow.csv"
            calibration = root / "calibration.json"
            _write_shadow(
                shadow,
                [
                    ("a.jpg", "b.jpg", 0.95, "same"),
                    ("b.jpg", "c.jpg", 0.80, "same"),
                    ("c.jpg", "d.jpg", 0.20, "different"),
                    ("d.jpg", "e.jpg", 0.45, "different"),
                    ("e.jpg", "f.jpg", 0.92, "same"),
                ],
            )
            _write_calibration(calibration)

            summary, evidence = simulate_routing(shadow, calibration)

            self.assertEqual(summary["mode"], "simulation")
            self.assertFalse(summary["production_routing_enabled"])
            self.assertEqual(summary["actual_provider_calls_skipped"], 0)
            self.assertEqual(summary["adjacent_boundaries"], 5)
            self.assertEqual(summary["local_routed_boundaries"], 3)
            self.assertEqual(summary["vision_boundaries_remaining"], 2)
            self.assertAlmostEqual(summary["local_routing_coverage"], 3 / 5)
            self.assertEqual(summary["unsafe_local_misroutes"], 0)
            self.assertEqual(summary["local_routing_accuracy"], 1.0)
            self.assertTrue(summary["safe_on_supplied_labels"])
            self.assertEqual(
                [row["routing_decision"] for row in evidence],
                ["local_same", "vision", "local_different", "vision", "local_same"],
            )

    def test_confident_wrong_route_is_never_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shadow = root / "shadow.csv"
            calibration = root / "calibration.json"
            _write_shadow(shadow, [("a.jpg", "b.jpg", 0.97, "different")])
            _write_calibration(calibration)

            summary, _ = simulate_routing(shadow, calibration)

            self.assertEqual(summary["local_routed_boundaries"], 1)
            self.assertEqual(summary["unsafe_local_misroutes"], 1)
            self.assertEqual(summary["local_routing_accuracy"], 0.0)
            self.assertFalse(summary["safe_on_supplied_labels"])

    def test_reports_and_cli_are_standalone_and_do_not_skip_provider_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shadow = root / "shadow.csv"
            calibration = root / "calibration.json"
            output = root / "reports"
            _write_shadow(
                shadow,
                [
                    ("a.jpg", "b.jpg", 0.95, "same"),
                    ("b.jpg", "c.jpg", 0.50, "different"),
                    ("c.jpg", "d.jpg", 0.20, "different"),
                ],
            )
            _write_calibration(calibration)

            summary, json_path, md_path, csv_path = simulate_from_files(
                shadow,
                calibration,
                output_dir=output,
            )
            self.assertEqual(summary["actual_provider_calls_skipped"], 0)
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertTrue(csv_path.is_file())
            self.assertIn("Production Hybrid Routing remains disabled", md_path.read_text(encoding="utf-8"))

            cli_output = root / "cli-reports"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "product_sorter.py"),
                    "--simulate-hybrid-routing",
                    str(shadow),
                    "--routing-calibration",
                    str(calibration),
                    "--routing-output",
                    str(cli_output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertIn("Production routing remains disabled", result.stdout)
            self.assertTrue((cli_output / "hybrid_routing_simulation.json").is_file())
            cli_summary = json.loads(
                (cli_output / "hybrid_routing_simulation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cli_summary["actual_provider_calls_skipped"], 0)
            self.assertFalse(cli_summary["production_routing_enabled"])


if __name__ == "__main__":
    unittest.main()
