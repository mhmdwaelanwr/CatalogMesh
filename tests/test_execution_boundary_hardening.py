import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.approval_boundary import create_approval_request
from ai_product_photo_sorter.execution_control import idempotency_key, validate_retry_policy
from ai_product_photo_sorter.shopify_execution import ACTION as SHOPIFY_STAGE_ACTION, _validated_inputs


class ExecutionBoundaryHardeningTests(unittest.TestCase):
    def test_approval_payload_rejects_nested_credential_like_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "request.json"
            with self.assertRaisesRegex(ValueError, "credential-like"):
                create_approval_request("safe.action", {"nested": {"client-secret": "nope"}}, output)
            self.assertFalse(output.exists())

    def test_retry_policy_requires_exact_types_ranges_and_known_fields(self):
        self.assertEqual(validate_retry_policy({"max_attempts": 2, "base_delay_seconds": 1, "max_delay_seconds": 4})["max_attempts"], 2)
        for policy in (
            {"max_attempts": True, "base_delay_seconds": 1, "max_delay_seconds": 2},
            {"max_attempts": 11, "base_delay_seconds": 1, "max_delay_seconds": 2},
            {"max_attempts": 2, "base_delay_seconds": -1, "max_delay_seconds": 2},
            {"max_attempts": 2, "base_delay_seconds": 3, "max_delay_seconds": 2},
            {"max_attempts": 2, "base_delay_seconds": 1, "max_delay_seconds": 2, "surprise": 1},
        ):
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):
                    validate_retry_policy(policy)

    def _shopify_pair(self, root: Path, payload: dict):
        request_id = "apr_test"
        request = {
            "schema_version": 1,
            "mode": "approval_request",
            "request_id": request_id,
            "action": SHOPIFY_STAGE_ACTION,
            "payload": payload,
        }
        reservation = {
            "schema_version": 1,
            "mode": "execution_reservation",
            "request_id": request_id,
            "action": SHOPIFY_STAGE_ACTION,
            "idempotency_key": idempotency_key(request_id, SHOPIFY_STAGE_ACTION, payload),
            "status": "reserved",
            "retry_policy": {"max_attempts": 1, "base_delay_seconds": 0.0, "max_delay_seconds": 0.0},
        }
        request_path = root / "request.json"
        reservation_path = root / "reservation.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        reservation_path.write_text(json.dumps(reservation), encoding="utf-8")
        return request_path, reservation_path

    def test_shopify_stage_requires_explicit_store_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, reservation = self._shopify_pair(root, {"export_manifest": str(root / "export.json"), "upload_images": False})
            with self.assertRaisesRegex(ValueError, "store_domain"):
                _validated_inputs(request, reservation)

    def test_shopify_stage_rejects_string_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, reservation = self._shopify_pair(root, {"export_manifest": str(root / "export.json"), "store_domain": "demo.myshopify.com", "upload_images": "false"})
            with self.assertRaisesRegex(ValueError, "JSON boolean"):
                _validated_inputs(request, reservation)

    def test_legacy_shopify_remote_mutation_surfaces_are_not_installed(self):
        package = Path(__file__).resolve().parents[1] / "src" / "ai_product_photo_sorter"
        core = (package / "core.py").read_text(encoding="utf-8")
        gui = (package / "gui.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_shopify_publishing(_impl)", core)
        self.assertNotIn("apply_shopify_publishing_gui(_impl)", gui)


if __name__ == "__main__":
    unittest.main()
