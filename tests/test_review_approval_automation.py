import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request, validate_grant
from ai_product_photo_sorter.review_automation import open_review_queue


class ReviewApprovalAutomationTests(unittest.TestCase):
    def test_open_review_queue_returns_only_pending_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "product_review_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mode": "review_manifest",
                        "output_root": str(root),
                        "source_report": str(root / "classification_report.csv"),
                        "revision": 1,
                        "audit_events": 2,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "groups": [
                            {
                                "group_id": "G1",
                                "category": "mouse",
                                "brand": "Demo",
                                "model": "A",
                                "approved": False,
                                "notes": "check angle",
                                "photos": [
                                    {
                                        "filename": "a.jpg",
                                        "view": "front",
                                        "confidence": 0.61,
                                        "original_status": "needs_review",
                                        "reason": "ambiguous",
                                        "relative_path": "Needs_Review/G1/a.jpg",
                                    }
                                ],
                            },
                            {
                                "group_id": "G2",
                                "category": "keyboard",
                                "brand": "Demo",
                                "model": "B",
                                "approved": True,
                                "notes": "",
                                "photos": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = open_review_queue(manifest)
            self.assertEqual(result["returned_groups"], 1)
            self.assertEqual(result["pending_groups"][0]["group_id"], "G1")
            self.assertTrue(result["read_only"])
            self.assertTrue(result["human_review_required"])

    def test_approval_requires_exact_human_confirmation_and_validates_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = root / "request.json"
            grant = root / "grant.json"
            create_approval_request("shopify.publish", {"product_id": "123"}, request)
            request_payload = json.loads(request.read_text(encoding="utf-8"))
            request_id = request_payload["request_id"]

            with self.assertRaisesRegex(ValueError, "Explicit confirmation required"):
                approve_request(request, grant, "yes")

            approve_request(request, grant, f"APPROVE {request_id}")
            result = validate_grant(request, grant)
            self.assertTrue(result["approved"])
            self.assertFalse(result["external_action_performed"])

            request_payload["payload"]["product_id"] = "changed"
            request.write_text(json.dumps(request_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "payload"):
                validate_grant(request, grant)


if __name__ == "__main__":
    unittest.main()
