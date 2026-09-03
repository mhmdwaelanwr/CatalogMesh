import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request
from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.execution_control import reserve_grant
from ai_product_photo_sorter.odoo_execution import ACTION, execute_odoo_products, reconcile_odoo_execution


class FakeOdooClient:
    def __init__(self, *, base_url="https://odoo.example.test", database="prod", products=None, fail_on=None):
        self.base_url = base_url
        self.database = database
        self.products = dict(products or {})
        self.fail_on = fail_on
        self.writes = []

    def find_product(self, default_code):
        value = self.products.get(default_code)
        return json.loads(json.dumps(value)) if value is not None else None

    def write_product(self, product_id, values):
        for code, product in self.products.items():
            if int(product["id"]) == int(product_id):
                if code == self.fail_on:
                    raise ValueError("Odoo request failed: injected")
                self.writes.append((product_id, json.loads(json.dumps(values))))
                product.update(json.loads(json.dumps(values)))
                return True
        return False


def _plan(root: Path, records=None):
    records = records or [
        {"identity": "SKU-1", "fields": {"default_code": "SKU-1", "name": "Mouse", "barcode": "111"}, "fingerprint": "fp1"},
        {"identity": "SKU-2", "fields": {"default_code": "SKU-2", "name": "Keyboard"}, "fingerprint": "fp2"},
    ]
    path = root / "connector_write_plan.json"
    path.write_text(json.dumps({"schema_version": 1, "mode": "catalog_connector_write_plan", "plan_id": "cplan_odoo", "profile_id": "odoo-products", "connector_kind": "erp", "entity": "product", "records": records, "network_calls_performed": 0, "external_action_performed": False}), encoding="utf-8")
    return path


def _reservation(root: Path, plan: Path, *, action=ACTION, base_url="https://odoo.example.test", database="prod"):
    request = root / "request.json"
    grant = root / "grant.json"
    create_approval_request(action, {"plan_path": str(plan), "plan_id": "cplan_odoo", "base_url": base_url, "database": database}, request)
    request_id = json.loads(request.read_text())["request_id"]
    approve_request(request, grant, f"APPROVE {request_id}")
    reserved = reserve_grant(request, grant, root / "control")
    return request, Path(reserved["reservation"])


class OdooExecutionTests(unittest.TestCase):
    def _client(self, **kwargs):
        products = {
            "SKU-1": {"id": 1, "default_code": "SKU-1", "name": "Old Mouse", "barcode": "101", "active": True},
            "SKU-2": {"id": 2, "default_code": "SKU-2", "name": "Old Keyboard", "barcode": False, "active": True},
        }
        return FakeOdooClient(products=products, **kwargs)

    def test_success_updates_existing_only_and_consumes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root); request, reservation = _reservation(root, plan); client = self._client()
            result = execute_odoo_products(request, reservation, client)
            self.assertEqual(result["records_applied"], 2)
            self.assertEqual(client.products["SKU-1"]["name"], "Mouse")
            self.assertEqual(json.loads(reservation.read_text())["status"], "succeeded")
            with self.assertRaisesRegex(ValueError, "not available"):
                execute_odoo_products(request, reservation, client)

    def test_missing_product_fails_before_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root); request, reservation = _reservation(root, plan)
            client = FakeOdooClient(products={"SKU-1": {"id": 1, "default_code": "SKU-1", "name": "Old", "barcode": False, "active": True}})
            with self.assertRaisesRegex(ValueError, "creation is out of scope"):
                execute_odoo_products(request, reservation, client)
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_wrong_action_cannot_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root); request, reservation = _reservation(root, plan, action="erp.apply_profile")
            with self.assertRaisesRegex(ValueError, ACTION):
                execute_odoo_products(request, reservation, self._client())

    def test_partial_failure_requires_reconciliation_no_auto_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root); request, reservation = _reservation(root, plan); client = self._client(fail_on="SKU-2")
            with self.assertRaisesRegex(ValueError, "execution failed"):
                execute_odoo_products(request, reservation, client)
            state = json.loads((root / "control" / "odoo_execution_state.json").read_text())
            self.assertTrue(state["reconciliation_required"])
            self.assertFalse(state["automatic_rollback_performed"])

    def test_reconcile_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = _plan(root); request, reservation = _reservation(root, plan); client = self._client()
            result = execute_odoo_products(request, reservation, client)
            writes_before = len(client.writes)
            report = reconcile_odoo_execution(result["state_path"], client)
            self.assertEqual(report["network_writes_performed"], 0)
            self.assertFalse(report["external_action_performed"])
            self.assertEqual(len(client.writes), writes_before)

    def test_cli_specific_no_generic_erp_executor(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["execute-odoo-products", "request.json", "reservation.json"]).command, "execute-odoo-products")
        self.assertEqual(parser.parse_args(["reconcile-odoo-execution", "state.json"]).command, "reconcile-odoo-execution")
        with self.assertRaises(SystemExit):
            parser.parse_args(["execute-erp"])


if __name__ == "__main__":
    unittest.main()
