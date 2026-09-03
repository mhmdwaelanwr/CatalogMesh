import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.akeneo_execution import ACTION, execute_akeneo_products, reconcile_akeneo_execution
from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request
from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.execution_control import reserve_grant


class FakeAkeneoClient:
    def __init__(self, base_url="https://demo.akeneo.test", existing=None, fail_on=None):
        self.base_url = base_url
        self.products = dict(existing or {})
        self.fail_on = fail_on
        self.patches = []
        self.reads = []

    def get_product(self, identifier):
        self.reads.append(identifier)
        value = self.products.get(identifier)
        return json.loads(json.dumps(value)) if value is not None else None

    def patch_product(self, identifier, payload):
        if identifier == self.fail_on:
            raise ValueError("Akeneo request failed: injected")
        self.patches.append((identifier, payload))
        self.products[identifier] = json.loads(json.dumps(payload))
        return {}


def _plan(root: Path, records=None):
    records = records or [
        {"row_number": 2, "identity": "SKU-1", "fields": {"identifier": "SKU-1", "values.name": "Mouse", "values.brand": "Mock"}, "fingerprint": "fp1"},
        {"row_number": 3, "identity": "SKU-2", "fields": {"identifier": "SKU-2", "values.name": "Keyboard"}, "fingerprint": "fp2"},
    ]
    path = root / "connector_write_plan.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "mode": "catalog_connector_write_plan",
        "plan_id": "cplan_test",
        "profile_id": "akeneo-products",
        "connector_kind": "pim",
        "entity": "product",
        "records": records,
        "network_calls_performed": 0,
        "external_action_performed": False,
        "human_approval_required": True,
    }), encoding="utf-8")
    return path


def _reservation(root: Path, plan: Path, *, action=ACTION, base_url="https://demo.akeneo.test"):
    request = root / "request.json"
    grant = root / "grant.json"
    create_approval_request(action, {"plan_path": str(plan), "plan_id": "cplan_test", "base_url": base_url}, request)
    request_id = json.loads(request.read_text(encoding="utf-8"))["request_id"]
    approve_request(request, grant, f"APPROVE {request_id}")
    reserved = reserve_grant(request, grant, root / "control")
    return request, Path(reserved["reservation"])


class AkeneoExecutionTests(unittest.TestCase):
    def test_success_snapshots_before_writes_and_consumes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(root)
            request, reservation = _reservation(root, plan)
            client = FakeAkeneoClient(existing={"SKU-1": {"identifier": "SKU-1", "values": {"name": [{"data": "Old"}]}}})
            result = execute_akeneo_products(request, reservation, client)
            self.assertEqual(result["records_applied"], 2)
            self.assertEqual(client.reads, ["SKU-1", "SKU-2"])
            self.assertEqual([item[0] for item in client.patches], ["SKU-1", "SKU-2"])
            state = json.loads(Path(result["state_path"]).read_text(encoding="utf-8"))
            self.assertTrue(state["records"][0]["before_exists"])
            self.assertFalse(state["records"][1]["before_exists"])
            self.assertFalse(state["automatic_rollback_performed"])
            self.assertEqual(json.loads(reservation.read_text(encoding="utf-8"))["status"], "succeeded")
            with self.assertRaisesRegex(ValueError, "not available"):
                execute_akeneo_products(request, reservation, client)

    def test_wrong_action_cannot_use_akeneo_executor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root)
            request, reservation = _reservation(root, plan, action="pim.apply_profile")
            with self.assertRaisesRegex(ValueError, ACTION):
                execute_akeneo_products(request, reservation, FakeAkeneoClient())
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_base_url_binding_fails_before_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root)
            request, reservation = _reservation(root, plan)
            with self.assertRaisesRegex(ValueError, "base_url"):
                execute_akeneo_products(request, reservation, FakeAkeneoClient(base_url="https://other.akeneo.test"))
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_invalid_akeneo_target_mapping_fails_before_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(root, [{"identity": "SKU-1", "fields": {"name": "Mouse"}, "fingerprint": "fp"}])
            request, reservation = _reservation(root, plan)
            with self.assertRaisesRegex(ValueError, "Unsupported Akeneo target field"):
                execute_akeneo_products(request, reservation, FakeAkeneoClient())
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_partial_failure_requires_reconciliation_and_never_auto_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root)
            request, reservation = _reservation(root, plan)
            client = FakeAkeneoClient(fail_on="SKU-2")
            with self.assertRaisesRegex(ValueError, "execution failed"):
                execute_akeneo_products(request, reservation, client)
            state_path = root / "control" / "akeneo_execution_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(state["reconciliation_required"])
            self.assertFalse(state["automatic_rollback_performed"])
            self.assertEqual(state["records"][0]["write_status"], "applied")
            self.assertEqual(state["records"][1]["write_status"], "pending")

    def test_reconciliation_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root)
            request, reservation = _reservation(root, plan)
            client = FakeAkeneoClient()
            result = execute_akeneo_products(request, reservation, client)
            patches_before = len(client.patches)
            report = reconcile_akeneo_execution(result["state_path"], client)
            self.assertEqual(report["network_writes_performed"], 0)
            self.assertFalse(report["external_action_performed"])
            self.assertEqual(len(client.patches), patches_before)

    def test_cli_exposes_specific_akeneo_commands_not_generic_executor(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["execute-akeneo-products", "request.json", "reservation.json"]).command, "execute-akeneo-products")
        self.assertEqual(parser.parse_args(["reconcile-akeneo-execution", "state.json"]).command, "reconcile-akeneo-execution")
        with self.assertRaises(SystemExit):
            parser.parse_args(["execute-connector"])


if __name__ == "__main__":
    unittest.main()
