import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.connector_profiles import build_connector_plan, load_connector_profile


class ConnectorProfileTests(unittest.TestCase):
    def _export(self, root: Path, *, sku: str = "SKU-1") -> Path:
        pim = root / "catalog_confirmed_products.csv"
        with pim.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["sku", "title", "price", "brand"])
            writer.writeheader(); writer.writerow({"sku": sku, "title": "Mouse", "price": "399", "brand": "Mock"})
        manifest = root / "catalog_export_manifest.json"
        manifest.write_text(json.dumps({"mode": "catalog_export_profiles", "products": 1, "publishing_enabled": False, "network_calls_performed": 0, "outputs": {"neutral_pim_csv": str(pim)}}), encoding="utf-8")
        return manifest

    def _profile(self, root: Path, **extra) -> Path:
        payload = {"schema_version": 1, "mode": "catalog_connector_profile", "profile_id": "mock-pim", "connector_kind": "pim", "entity": "product", "identity_source": "sku", "field_map": {"sku": "code", "title": "name", "price": "price"}, "required_source_fields": ["sku", "title"]}
        payload.update(extra)
        path = root / "profile.json"; path.write_text(json.dumps(payload), encoding="utf-8"); return path

    def test_build_plan_maps_only_declared_fields_and_performs_zero_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, path = build_connector_plan(self._export(root), self._profile(root))
            self.assertTrue(path.is_file())
            self.assertEqual(plan["action"], "pim.apply_profile")
            self.assertEqual(plan["network_calls_performed"], 0)
            self.assertFalse(plan["external_action_performed"])
            self.assertTrue(plan["human_approval_required"])
            self.assertEqual(plan["records"][0]["identity"], "SKU-1")
            self.assertEqual(plan["records"][0]["fields"], {"code": "SKU-1", "name": "Mouse", "price": "399"})

    def test_profile_rejects_embedded_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "credential"):
                load_connector_profile(self._profile(root, api_token="secret"))

    def test_missing_required_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "missing required"):
                build_connector_plan(self._export(root, sku=""), self._profile(root))

    def test_duplicate_target_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "multiple source fields"):
                load_connector_profile(self._profile(root, field_map={"sku": "id", "title": "id"}))

    def test_cli_exposes_plan_preparation_but_not_generic_execute(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["prepare-connector-plan", "export.json", "profile.json"]).command, "prepare-connector-plan")
        with self.assertRaises(SystemExit):
            parser.parse_args(["execute-connector"])


if __name__ == "__main__":
    unittest.main()
