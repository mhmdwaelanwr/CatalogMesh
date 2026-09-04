import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ai_product_photo_sorter import automation_cli


REQUIRED_LOCAL_WORKFLOW_COMMANDS = {
    "review-init",
    "review-summary",
    "review-apply",
    "review-export-approved",
    "sku-generate",
    "sku-confirm",
    "sku-clear",
    "export-catalog",
}


def _command_names() -> set[str]:
    parser = automation_cli.build_parser()
    names: set[str] = set()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            names.update(choices)
    return names


class WorkflowAutomationCliTests(unittest.TestCase):
    def test_local_workflow_commands_are_first_class_automation_commands(self):
        self.assertTrue(REQUIRED_LOCAL_WORKFLOW_COMMANDS.issubset(_command_names()))

    @mock.patch("ai_product_photo_sorter.automation_cli.review_summary", return_value={"groups": 2})
    @mock.patch("ai_product_photo_sorter.automation_cli.initialize_review")
    def test_review_init_uses_shared_review_backend(self, initialize, _summary):
        initialize.return_value = ({"groups": []}, Path("/tmp/product_review_manifest.json"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(automation_cli.main(["review-init", "/tmp/output"]), 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["summary"]["groups"], 2)
        initialize.assert_called_once_with(Path("/tmp/output"))

    @mock.patch("ai_product_photo_sorter.automation_cli.review_summary", return_value={"approved_groups": 1})
    @mock.patch("ai_product_photo_sorter.automation_cli.apply_review_plan")
    def test_review_apply_uses_shared_review_plan_backend(self, apply_plan, _summary):
        apply_plan.return_value = ({"groups": []}, Path("/tmp/product_review_manifest.json"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                automation_cli.main([
                    "review-apply",
                    "/tmp/product_review_manifest.json",
                    "/tmp/review-plan.json",
                ]),
                0,
            )
        self.assertEqual(json.loads(out.getvalue())["summary"]["approved_groups"], 1)
        apply_plan.assert_called_once_with(
            Path("/tmp/product_review_manifest.json"),
            Path("/tmp/review-plan.json"),
        )

    @mock.patch("ai_product_photo_sorter.automation_cli.export_approved")
    def test_review_export_uses_shared_summary_contract(self, export):
        export.return_value = (
            {"approved_groups": 2, "pending_groups": 0, "catalog_ready": True},
            Path("/tmp/approved_product_groups.csv"),
        )
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                automation_cli.main([
                    "review-export-approved",
                    "/tmp/product_review_manifest.json",
                    "--approved-out",
                    "/tmp/approved_product_groups.csv",
                ]),
                0,
            )
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["summary"]["approved_groups"], 2)
        export.assert_called_once_with(
            Path("/tmp/product_review_manifest.json"),
            Path("/tmp/approved_product_groups.csv"),
        )

    @mock.patch("ai_product_photo_sorter.automation_cli.confirm_candidate")
    def test_sku_confirm_keeps_human_confirmation_backend(self, confirm):
        confirm.return_value = (
            {"summary": {"confirmed_groups": 1, "human_confirmation_required": True}},
            Path("/tmp/sku_match_manifest.json"),
        )
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                automation_cli.main([
                    "sku-confirm",
                    "/tmp/sku_match_manifest.json",
                    "Group_0001",
                    "Catalog!R4",
                ]),
                0,
            )
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["summary"]["confirmed_groups"], 1)
        confirm.assert_called_once_with(
            Path("/tmp/sku_match_manifest.json"),
            "Group_0001",
            "Catalog!R4",
        )

    @mock.patch("ai_product_photo_sorter.automation_cli.clear_confirmation")
    def test_sku_clear_uses_shared_backend(self, clear):
        clear.return_value = (
            {"summary": {"confirmed_groups": 0, "human_confirmation_required": True}},
            Path("/tmp/sku_match_manifest.json"),
        )
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                automation_cli.main([
                    "sku-clear",
                    "/tmp/sku_match_manifest.json",
                    "Group_0001",
                ]),
                0,
            )
        clear.assert_called_once_with(Path("/tmp/sku_match_manifest.json"), "Group_0001")

    @mock.patch("ai_product_photo_sorter.automation_cli.generate_exports")
    def test_export_catalog_supports_all_safe_profiles(self, generate):
        generate.return_value = ({"products": 3}, Path("/tmp/exports/catalog_export_manifest.json"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                automation_cli.main([
                    "export-catalog",
                    "/tmp/sku_match_manifest.json",
                    "--output",
                    "/tmp/exports",
                    "--profile",
                    "pim",
                ]),
                0,
            )
        self.assertEqual(json.loads(out.getvalue())["summary"]["products"], 3)
        generate.assert_called_once_with(
            Path("/tmp/sku_match_manifest.json"),
            output_dir=Path("/tmp/exports"),
            profile="pim",
        )


if __name__ == "__main__":
    unittest.main()
