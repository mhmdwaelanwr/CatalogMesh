from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request
from ai_product_photo_sorter.execution_control import reserve_grant
from ai_product_photo_sorter.shopify_execution import ACTION, execute_shopify_stage


class ShopifyExecutionTests(unittest.TestCase):
    def make_reservation(self, root: Path, *, store_domain: str = "mock-store.myshopify.com") -> tuple[Path, Path, Path]:
        payload = {
            "export_manifest": str(root / "catalog_export_manifest.json"),
            "output_dir": str(root / "remote"),
            "upload_images": False,
            "store_domain": store_domain,
        }
        request = root / "request.json"
        grant = root / "grant.json"
        create_approval_request(ACTION, payload, request)
        request_id = json.loads(request.read_text(encoding="utf-8"))["request_id"]
        approve_request(request, grant, f"APPROVE {request_id}")
        record = reserve_grant(
            request,
            grant,
            root / "control",
            retry_policy={"max_attempts": 3, "base_delay_seconds": 0, "max_delay_seconds": 0},
        )
        return request, grant, Path(record["reservation"])

    def test_success_consumes_reservation_and_stays_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request, _, reservation = self.make_reservation(root)
            client = SimpleNamespace(store_domain="mock-store.myshopify.com")
            state_path = root / "remote" / "shopify_publish_manifest.json"
            with patch("ai_product_photo_sorter.shopify_execution.stage_drafts", return_value=({"products": {"SKU1": {}}}, state_path)) as stage:
                result = execute_shopify_stage(request, reservation, client)
            self.assertEqual(stage.call_count, 1)
            self.assertEqual(result["remote_status"], "DRAFT")
            self.assertFalse(result["published"])
            stored = json.loads(reservation.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "succeeded")
            self.assertTrue(stored["external_action_performed"])
            with self.assertRaisesRegex(ValueError, "not available"):
                execute_shopify_stage(request, reservation, client)

    def test_transient_failure_retries_under_same_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request, _, reservation = self.make_reservation(root)
            client = SimpleNamespace(store_domain="mock-store.myshopify.com")
            state_path = root / "remote" / "shopify_publish_manifest.json"
            effects = [ValueError("Shopify request failed: timeout"), ({"products": {}}, state_path)]
            with patch("ai_product_photo_sorter.shopify_execution.stage_drafts", side_effect=effects) as stage:
                result = execute_shopify_stage(request, reservation, client, sleep=lambda _: None)
            self.assertEqual(stage.call_count, 2)
            stored = json.loads(reservation.read_text(encoding="utf-8"))
            self.assertEqual(stored["attempts"], 2)
            self.assertEqual(stored["idempotency_key"], result["idempotency_key"])

    def test_nonretryable_guard_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request, _, reservation = self.make_reservation(root)
            client = SimpleNamespace(store_domain="mock-store.myshopify.com")
            with patch("ai_product_photo_sorter.shopify_execution.stage_drafts", side_effect=ValueError("Blocked duplicate Shopify SKU")) as stage:
                with self.assertRaisesRegex(ValueError, "failed after 1 attempt"):
                    execute_shopify_stage(request, reservation, client)
            self.assertEqual(stage.call_count, 1)
            stored = json.loads(reservation.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "failed")

    def test_store_mismatch_does_not_consume_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request, _, reservation = self.make_reservation(root)
            client = SimpleNamespace(store_domain="other-store.myshopify.com")
            with self.assertRaisesRegex(ValueError, "store domain"):
                execute_shopify_stage(request, reservation, client)
            stored = json.loads(reservation.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "reserved")

    def test_tampered_request_is_rejected_before_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request, _, reservation = self.make_reservation(root)
            payload = json.loads(request.read_text(encoding="utf-8"))
            payload["payload"]["export_manifest"] = str(root / "different.json")
            request.write_text(json.dumps(payload), encoding="utf-8")
            client = SimpleNamespace(store_domain="mock-store.myshopify.com")
            with self.assertRaisesRegex(ValueError, "idempotency key"):
                execute_shopify_stage(request, reservation, client)
            stored = json.loads(reservation.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "reserved")


if __name__ == "__main__":
    unittest.main()
