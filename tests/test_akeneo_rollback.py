import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.akeneo_execution import ACTION as APPLY_ACTION, _fingerprint, execute_akeneo_products
from ai_product_photo_sorter.akeneo_rollback import ACTION as ROLLBACK_ACTION, execute_akeneo_rollback
from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request
from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.execution_control import reserve_grant


class FakeAkeneoClient:
    def __init__(self, existing=None):
        self.base_url = "https://demo.akeneo.test"
        self.products = dict(existing or {})
        self.patches = []

    def get_product(self, identifier):
        value = self.products.get(identifier)
        return json.loads(json.dumps(value)) if value is not None else None

    def patch_product(self, identifier, payload):
        self.patches.append((identifier, json.loads(json.dumps(payload))))
        current = self.products.setdefault(identifier, {"identifier": identifier})
        current.update(json.loads(json.dumps(payload)))
        return {}


def reserve(root, action, payload):
    request = root / f"{action.replace('.', '_')}_request.json"
    grant = root / f"{action.replace('.', '_')}_grant.json"
    create_approval_request(action, payload, request)
    request_id = json.loads(request.read_text())["request_id"]
    approve_request(request, grant, f"APPROVE {request_id}")
    result = reserve_grant(request, grant, root / f"control-{action.replace('.', '-')}")
    return request, Path(result["reservation"])


def rollback_payload(state: Path, client: FakeAkeneoClient):
    payload = json.loads(state.read_text(encoding="utf-8"))
    expected = {}
    for item in payload["records"]:
        if item.get("write_status") == "applied" and item.get("before_exists"):
            expected[item["identity"]] = _fingerprint(client.get_product(item["identity"]))
    return {
        "state_path": str(state),
        "plan_id": "cplan_test",
        "base_url": client.base_url,
        "expected_current_fingerprints": expected,
    }


class AkeneoRollbackTests(unittest.TestCase):
    def _applied_state(self, root, *, include_created=False):
        records = [{"identity": "SKU-1", "fields": {"identifier": "SKU-1", "values.name": "New"}, "fingerprint": "fp1"}]
        if include_created:
            records.append({"identity": "SKU-2", "fields": {"identifier": "SKU-2", "values.name": "Created"}, "fingerprint": "fp2"})
        plan = root / "plan.json"
        plan.write_text(json.dumps({"schema_version": 1, "mode": "catalog_connector_write_plan", "plan_id": "cplan_test", "profile_id": "akeneo-products", "connector_kind": "pim", "entity": "product", "records": records, "network_calls_performed": 0, "external_action_performed": False}), encoding="utf-8")
        request, reservation = reserve(root, APPLY_ACTION, {"plan_path": str(plan), "plan_id": "cplan_test", "base_url": "https://demo.akeneo.test"})
        existing = {"SKU-1": {"identifier": "SKU-1", "enabled": True, "values": {"name": [{"locale": None, "scope": None, "data": "Old"}]}}}
        client = FakeAkeneoClient(existing)
        result = execute_akeneo_products(request, reservation, client, state_path=root / "state.json")
        return Path(result["state_path"]), client

    def test_rollback_requires_fresh_action_and_restores_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, client = self._applied_state(root)
            request, reservation = reserve(root, ROLLBACK_ACTION, rollback_payload(state, client))
            result = execute_akeneo_rollback(request, reservation, client)
            self.assertEqual(result["records_restored"], 1)
            self.assertEqual(client.products["SKU-1"]["values"]["name"][0]["data"], "Old")
            self.assertEqual(json.loads(reservation.read_text())["status"], "succeeded")
            with self.assertRaisesRegex(ValueError, "not available"):
                execute_akeneo_rollback(request, reservation, client)

    def test_remote_drift_blocks_before_reservation_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, client = self._applied_state(root)
            request, reservation = reserve(root, ROLLBACK_ACTION, rollback_payload(state, client))
            client.products["SKU-1"]["values"]["name"][0]["data"] = "Changed after approval"
            patches_before = len(client.patches)
            with self.assertRaisesRegex(ValueError, "drifted after reconciliation"):
                execute_akeneo_rollback(request, reservation, client)
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")
            self.assertEqual(len(client.patches), patches_before)

    def test_missing_fresh_fingerprints_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, client = self._applied_state(root)
            request, reservation = reserve(root, ROLLBACK_ACTION, {"state_path": str(state), "plan_id": "cplan_test", "base_url": client.base_url})
            with self.assertRaisesRegex(ValueError, "fresh read-only reconciliation"):
                execute_akeneo_rollback(request, reservation, client)
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_apply_approval_cannot_be_reused_for_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, client = self._applied_state(root)
            payload = rollback_payload(state, client)
            request, reservation = reserve(root, APPLY_ACTION, payload)
            with self.assertRaisesRegex(ValueError, ROLLBACK_ACTION):
                execute_akeneo_rollback(request, reservation, client)

    def test_created_product_fails_closed_instead_of_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, client = self._applied_state(root, include_created=True)
            request, reservation = reserve(root, ROLLBACK_ACTION, rollback_payload(state, client))
            with self.assertRaisesRegex(ValueError, "separate explicitly approved action"):
                execute_akeneo_rollback(request, reservation, client)
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_cli_is_specific_not_generic(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["execute-akeneo-rollback", "request.json", "reservation.json"]).command, "execute-akeneo-rollback")
        with self.assertRaises(SystemExit):
            parser.parse_args(["rollback-connector"])


if __name__ == "__main__":
    unittest.main()
