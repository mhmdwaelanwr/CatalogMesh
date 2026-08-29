from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ai_product_photo_sorter.review_center import (
    APPROVED_NAME,
    AUDIT_NAME,
    MANIFEST_NAME,
    SUMMARY_NAME,
    apply_review_plan,
    export_approved,
    initialize_review,
    load_manifest,
    review_summary,
)


ROOT = Path(__file__).resolve().parent.parent


class ReviewCenterTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        output = root / "output"
        output.mkdir()
        rows = [
            {
                "filename": "A_front.jpg",
                "output_filename": "A_front.jpg",
                "taken_at": "2026-08-29 01:00:00",
                "product_group": "Product_0001_Mouse_M100",
                "category": "mouse",
                "view": "front",
                "brand": "MockLab",
                "model": "M100",
                "catalog_match": "",
                "confidence": "0.94",
                "status": "classified",
                "reason": "mock",
            },
            {
                "filename": "A_back.jpg",
                "output_filename": "A_back.jpg",
                "taken_at": "2026-08-29 01:00:01",
                "product_group": "Product_0001_Mouse_M100",
                "category": "mouse",
                "view": "back",
                "brand": "MockLab",
                "model": "M100",
                "catalog_match": "",
                "confidence": "0.91",
                "status": "classified",
                "reason": "mock",
            },
            {
                "filename": "B_front.jpg",
                "output_filename": "B_front.jpg",
                "taken_at": "2026-08-29 01:00:02",
                "product_group": "Product_0002_Mouse_M110",
                "category": "mouse",
                "view": "front",
                "brand": "MockLab",
                "model": "M110",
                "catalog_match": "",
                "confidence": "0.63",
                "status": "needs_review",
                "reason": "lookalike variant",
            },
            {
                "filename": "B_back.jpg",
                "output_filename": "B_back.jpg",
                "taken_at": "2026-08-29 01:00:03",
                "product_group": "Product_0002_Mouse_M110",
                "category": "mouse",
                "view": "back",
                "brand": "MockLab",
                "model": "M110",
                "catalog_match": "",
                "confidence": "0.66",
                "status": "needs_review",
                "reason": "lookalike variant",
            },
        ]
        fields = list(rows[0])
        with (output / "classification_report.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        for row in rows:
            parent = (
                "Needs_Review"
                if row["status"] == "needs_review"
                else row["category"]
            )
            photo_dir = output / parent / row["product_group"]
            photo_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (80, 60), (230, 230, 230)).save(
                photo_dir / row["output_filename"], "JPEG"
            )
        return output

    def _plan(self, root: Path, operations: list[dict]) -> Path:
        path = root / "plan.json"
        path.write_text(
            json.dumps({"operations": operations}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def test_initialize_builds_manifest_without_touching_photo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._fixture(root)
            before = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*.jpg")
            }

            manifest, path = initialize_review(output)
            summary = review_summary(manifest)

            self.assertEqual(path, output / MANIFEST_NAME)
            self.assertTrue(path.is_file())
            self.assertTrue((output / SUMMARY_NAME).is_file())
            self.assertEqual(summary["groups"], 2)
            self.assertEqual(summary["photos"], 4)
            self.assertEqual(summary["approved_groups"], 0)
            self.assertEqual(summary["pending_groups"], 2)
            self.assertEqual(summary["needs_review_photos"], 2)
            self.assertFalse(summary["catalog_ready"])
            group_a, group_b = manifest["groups"]
            self.assertEqual(group_a["photos"][0]["relative_path"], "mouse/Product_0001_Mouse_M100/A_front.jpg")
            self.assertEqual(group_b["photos"][0]["relative_path"], "Needs_Review/Product_0002_Mouse_M110/B_front.jpg")

            after = {
                photo.relative_to(output).as_posix(): photo.read_bytes()
                for photo in output.rglob("*.jpg")
            }
            self.assertEqual(before, after)

    def test_corrections_reset_approval_and_audit_every_persisted_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._fixture(root)
            _, manifest_path = initialize_review(output)

            approve = self._plan(
                root,
                [{"action": "approve", "group": "Product_0001_Mouse_M100"}],
            )
            manifest, _ = apply_review_plan(manifest_path, approve)
            self.assertTrue(manifest["groups"][0]["approved"])

            edit = self._plan(
                root,
                [
                    {
                        "action": "set_group",
                        "group": "Product_0001_Mouse_M100",
                        "category": "mouse",
                        "brand": "MockLab",
                        "model": "M100-R",
                        "notes": "human corrected",
                    },
                    {
                        "action": "set_view",
                        "filename": "A_back.jpg",
                        "view": "detail",
                    },
                ],
            )
            manifest, _ = apply_review_plan(manifest_path, edit)
            group = next(
                item
                for item in manifest["groups"]
                if item["group_id"] == "Product_0001_Mouse_M100"
            )
            self.assertFalse(group["approved"])
            self.assertEqual(group["model"], "M100-R")
            self.assertEqual(group["notes"], "human corrected")
            photo = next(item for item in group["photos"] if item["filename"] == "A_back.jpg")
            self.assertEqual(photo["view"], "detail")
            self.assertEqual(manifest["revision"], 3)
            self.assertEqual(manifest["audit_events"], 3)

            audit_lines = (output / AUDIT_NAME).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(audit_lines), 3)
            events = [json.loads(line) for line in audit_lines]
            self.assertEqual([event["revision"] for event in events], [1, 2, 3])
            self.assertEqual([event["action"] for event in events], ["approve", "set_group", "set_view"])

    def test_split_move_merge_are_manifest_only_and_keep_review_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._fixture(root)
            before_paths = sorted(path.relative_to(output).as_posix() for path in output.rglob("*.jpg"))
            _, manifest_path = initialize_review(output)

            split = self._plan(
                root,
                [
                    {
                        "action": "split",
                        "group": "Product_0001_Mouse_M100",
                        "filenames": ["A_back.jpg"],
                        "new_group": "Product_0001B_Mouse_M100",
                    }
                ],
            )
            manifest, _ = apply_review_plan(manifest_path, split)
            self.assertEqual(manifest["group_count"], 3)
            self.assertEqual(manifest["photo_count"], 4)

            move = self._plan(
                root,
                [
                    {
                        "action": "move_photo",
                        "filename": "A_back.jpg",
                        "to_group": "Product_0002_Mouse_M110",
                    }
                ],
            )
            manifest, _ = apply_review_plan(manifest_path, move)
            self.assertEqual(manifest["group_count"], 2)
            destination = next(
                item
                for item in manifest["groups"]
                if item["group_id"] == "Product_0002_Mouse_M110"
            )
            self.assertEqual(len(destination["photos"]), 3)
            self.assertFalse(destination["approved"])

            merge = self._plan(
                root,
                [
                    {
                        "action": "merge",
                        "groups": [
                            "Product_0001_Mouse_M100",
                            "Product_0002_Mouse_M110",
                        ],
                        "target": "Product_0001_Mouse_M100",
                    }
                ],
            )
            manifest, _ = apply_review_plan(manifest_path, merge)
            self.assertEqual(manifest["group_count"], 1)
            self.assertEqual(manifest["photo_count"], 4)
            self.assertEqual(manifest["pending_groups"], 1)
            self.assertFalse(manifest["catalog_ready"])

            after_paths = sorted(path.relative_to(output).as_posix() for path in output.rglob("*.jpg"))
            self.assertEqual(before_paths, after_paths)

    def test_approved_export_never_includes_pending_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._fixture(root)
            _, manifest_path = initialize_review(output)
            plan = self._plan(
                root,
                [{"action": "approve", "group": "Product_0001_Mouse_M100"}],
            )
            apply_review_plan(manifest_path, plan)

            summary, approved_path = export_approved(manifest_path)
            self.assertEqual(approved_path, output / APPROVED_NAME)
            self.assertEqual(summary["approved_groups"], 1)
            self.assertEqual(summary["pending_groups"], 1)
            self.assertFalse(summary["catalog_ready"])
            with approved_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["group_id"], "Product_0001_Mouse_M100")
            self.assertNotIn("B_front.jpg", rows[0]["filenames"])

    def test_cli_review_actions_are_standalone_without_provider_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = self._fixture(root)

            init = subprocess.run(
                [sys.executable, str(ROOT / "product_sorter.py"), "--review-init", str(output)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(init.returncode, 0, init.stderr or init.stdout)
            self.assertIn("Review manifest:", init.stdout)
            manifest_path = output / MANIFEST_NAME
            self.assertTrue(manifest_path.is_file())

            plan = self._plan(
                root,
                [
                    {"action": "approve", "group": "Product_0001_Mouse_M100"},
                    {"action": "approve", "group": "Product_0002_Mouse_M110"},
                ],
            )
            apply_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "product_sorter.py"),
                    "--review-apply",
                    str(manifest_path),
                    "--review-plan",
                    str(plan),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr or apply_result.stdout)
            self.assertIn('"catalog_ready": true', apply_result.stdout.lower())

            export_result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "product_sorter.py"),
                    "--review-export-approved",
                    str(manifest_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(export_result.returncode, 0, export_result.stderr or export_result.stdout)
            self.assertTrue((output / APPROVED_NAME).is_file())
            manifest, _ = load_manifest(manifest_path)
            self.assertTrue(review_summary(manifest)["catalog_ready"])


if __name__ == "__main__":
    unittest.main()
