import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request
from ai_product_photo_sorter.execution_control import reserve_grant
from ai_product_photo_sorter.shopify_publication_gate import PUBLISH_ACTION, ROLLBACK_ACTION, execute_shopify_publish, execute_shopify_rollback


class FakeClient:
    store_domain = "mock-store.myshopify.com"


def _state(path: Path, published: bool = False) -> Path:
    path.write_text(json.dumps({"mode": "shopify_publish_state", "store_domain": "mock-store.myshopify.com", "products": {"SKU1": {"published": published, "stage_status": "published" if published else "draft_staged"}}}), encoding="utf-8")
    return path


def _reservation(root: Path, action: str, payload: dict):
    request = root / "request.json"; grant = root / "grant.json"; state_dir = root / "control"
    create_approval_request(action, payload, request)
    request_id = json.loads(request.read_text())["request_id"]
    approve_request(request, grant, f"APPROVE {request_id}")
    reserved = reserve_grant(request, grant, state_dir)
    return request, Path(reserved["reservation"])


class ShopifyPublicationGateTests(unittest.TestCase):
    def test_publish_requires_separate_publish_action_and_consumes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = _state(root / "state.json")
            request, reservation = _reservation(root, PUBLISH_ACTION, {"state_path": str(state), "store_domain": FakeClient.store_domain, "publication_id": "gid://shopify/Publication/1"})
            with patch("ai_product_photo_sorter.shopify_publication_gate.publish_staged", return_value=({"products": {"SKU1": {"published": True}}}, state)) as publish:
                result = execute_shopify_publish(request, reservation, FakeClient())
                self.assertTrue(result["published"]); publish.assert_called_once()
            with self.assertRaisesRegex(ValueError, "not available"):
                execute_shopify_publish(request, reservation, FakeClient())

    def test_stage_approval_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = _state(root / "state.json")
            request, reservation = _reservation(root, "shopify.stage_drafts", {"state_path": str(state)})
            with self.assertRaisesRegex(ValueError, PUBLISH_ACTION):
                execute_shopify_publish(request, reservation, FakeClient())

    def test_publish_rejects_store_or_publication_mismatch_before_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = _state(root / "state.json")
            request, reservation = _reservation(root, PUBLISH_ACTION, {"state_path": str(state), "store_domain": "other.myshopify.com", "publication_id": "gid://shopify/Publication/1"})
            with self.assertRaisesRegex(ValueError, "store domain"):
                execute_shopify_publish(request, reservation, FakeClient())
            self.assertEqual(json.loads(reservation.read_text())["status"], "reserved")

    def test_rollback_has_its_own_human_approval_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); state = _state(root / "state.json", published=True)
            request, reservation = _reservation(root, ROLLBACK_ACTION, {"state_path": str(state), "store_domain": FakeClient.store_domain})
            with patch("ai_product_photo_sorter.shopify_publication_gate.rollback_publication", return_value=({"products": {"SKU1": {"published": False}}}, state)) as rollback:
                result = execute_shopify_rollback(request, reservation, FakeClient())
                self.assertTrue(result["rolled_back"]); rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
