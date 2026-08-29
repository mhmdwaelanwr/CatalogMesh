import csv
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.threshold_calibration import (
    LabeledBoundary,
    calibrate_from_files,
    calibrate_thresholds,
    validate_ground_truth,
    write_ground_truth_template,
)


class ThresholdCalibrationTests(unittest.TestCase):
    def test_template_contains_product_group_and_only_supported_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "photos"
            source.mkdir()
            (source / "b.jpeg").write_bytes(b"x")
            (source / "a.jpg").write_bytes(b"x")
            (source / "ignore.png").write_bytes(b"x")
            output = root / "truth.csv"

            summary = write_ground_truth_template(source, output)

            self.assertEqual(summary["photos"], 2)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["filename"] for row in rows], ["a.jpg", "b.jpeg"])
            self.assertIn("product_group", rows[0])

    def test_validation_requires_complete_unique_product_group_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "photos"
            source.mkdir()
            for name in ("1.jpg", "2.jpg", "3.jpg"):
                (source / name).write_bytes(b"x")
            truth = root / "truth.csv"
            truth.write_text(
                "filename,category,view,brand,model,product_group\n"
                "1.jpg,,,,,P1\n2.jpg,,,,,P1\n3.jpg,,,,,P2\n",
                encoding="utf-8",
            )
            summary = validate_ground_truth(source, truth)
            self.assertTrue(summary["valid_for_calibration"])
            self.assertEqual(summary["unique_product_groups"], 2)
            self.assertEqual(summary["product_group_coverage"], 1.0)

    def test_calibration_maximizes_coverage_subject_to_precision(self):
        boundaries = [
            LabeledBoundary("a", "b", 0.94, True),
            LabeledBoundary("b", "c", 0.92, True),
            LabeledBoundary("c", "d", 0.89, True),
            LabeledBoundary("d", "e", 0.86, True),
            LabeledBoundary("e", "f", 0.55, False),
            LabeledBoundary("f", "g", 0.45, False),
            LabeledBoundary("g", "h", 0.35, False),
            LabeledBoundary("h", "i", 0.20, False),
        ]
        result = calibrate_thresholds(
            boundaries,
            minimum_precision=1.0,
            minimum_boundaries=4,
            minimum_decisions=2,
        )
        self.assertTrue(result["promotion_ready"])
        self.assertAlmostEqual(result["same_threshold"], 0.86)
        self.assertAlmostEqual(result["different_threshold"], 0.55)
        self.assertEqual(result["confident_coverage"], 1.0)
        self.assertEqual(result["confident_accuracy"], 1.0)

    def test_overlap_is_kept_ambiguous_instead_of_sacrificing_precision(self):
        boundaries = [
            LabeledBoundary("a", "b", 0.95, True),
            LabeledBoundary("b", "c", 0.91, True),
            LabeledBoundary("c", "d", 0.70, True),
            LabeledBoundary("d", "e", 0.72, False),
            LabeledBoundary("e", "f", 0.40, False),
            LabeledBoundary("f", "g", 0.10, False),
        ]
        result = calibrate_thresholds(
            boundaries,
            minimum_precision=1.0,
            minimum_boundaries=4,
            minimum_decisions=2,
        )
        self.assertAlmostEqual(result["same_threshold"], 0.91)
        self.assertAlmostEqual(result["different_threshold"], 0.40)
        self.assertEqual(result["confident_decisions"], 4)
        self.assertEqual(result["ambiguous_boundaries"], 2)
        self.assertAlmostEqual(result["confident_coverage"], 4 / 6)

    def test_calibration_from_shadow_can_join_external_product_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shadow = root / "shadow.csv"
            shadow.write_text(
                "previous_filename,filename,cosine_similarity,ground_truth_relation\n"
                "1.jpg,2.jpg,0.95,\n"
                "2.jpg,3.jpg,0.10,\n"
                "3.jpg,4.jpg,0.96,\n"
                "4.jpg,5.jpg,0.15,\n",
                encoding="utf-8",
            )
            truth = root / "truth.csv"
            truth.write_text(
                "filename,category,view,brand,model,product_group\n"
                "1.jpg,,,,,P1\n2.jpg,,,,,P1\n3.jpg,,,,,P2\n4.jpg,,,,,P2\n5.jpg,,,,,P3\n",
                encoding="utf-8",
            )
            result, json_path, md_path = calibrate_from_files(
                shadow,
                ground_truth=truth,
                output_dir=root / "out",
                minimum_precision=1.0,
                minimum_boundaries=4,
                minimum_decisions=2,
            )
            self.assertTrue(result["promotion_ready"])
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertIn("does not enable production routing", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
