import json
import tempfile
import unittest
from pathlib import Path

from ai_product_photo_sorter.approval_boundary import approve_request, create_approval_request
from ai_product_photo_sorter.automation_cli import build_parser
from ai_product_photo_sorter.execution_control import (
    idempotency_key,
    record_execution_result,
    redact_secrets,
    reserve_grant,
)


class ExecutionControlTests(unittest.TestCase):
    def _approved_pair(self, root: Path):
        request = root / "request.json"
        grant = root / "grant.json"
        payload = {
            "sku": "SKU-1",
            "nested": {"safe": "keep"},
        }
        create_approval_request("shopify.stage_draft", payload, request)
        request_payload = json.loads(request.read_text(encoding="utf-8"))
        approve_request(request, grant, f"APPROVE {request_payload['request_id']}")
        return request, grant, request_payload

    def test_reservation_is_single_use_and_preserves_safe_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, grant, request_payload = self._approved_pair(root)
            state = root / "state"

            reservation = reserve_grant(request, grant, state)
            self.assertEqual(reservation["status"], "reserved")
            self.assertFalse(reservation["external_action_performed"])
            self.assertEqual(reservation["redacted_payload"]["sku"], "SKU-1")
            self.assertEqual(reservation["redacted_payload"]["nested"]["safe"], "keep")
            self.assertTrue(Path(reservation["reservation"]).is_file())
            self.assertTrue((state / "execution_audit.jsonl").is_file())

            with self.assertRaisesRegex(ValueError, "already been reserved"):
                reserve_grant(request, grant, state)

            expected_key = idempotency_key(
                request_payload["request_id"],
                request_payload["action"],
                request_payload["payload"],
            )
            self.assertEqual(reservation["idempotency_key"], expected_key)

    def test_execution_result_appends_redacted_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, grant, _ = self._approved_pair(root)
            state = root / "state"
            reservation = reserve_grant(request, grant, state)
            audit = state / "execution_audit.jsonl"

            result = record_execution_result(
                reservation["reservation"],
                audit,
                status="failed",
                attempt=1,
                details={"password": "dont-log-me", "message": "timeout"},
                external_action_performed=False,
            )
            self.assertEqual(result["status"], "failed")
            lines = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[-1]["details"]["password"], "[REDACTED]")
            self.assertEqual(lines[-1]["details"]["message"], "timeout")

    def test_redaction_handles_nested_lists(self):
        payload = {"items": [{"token": "abc", "name": "ok"}], "authorization": "bearer x"}
        redacted = redact_secrets(payload)
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["items"][0]["token"], "[REDACTED]")
        self.assertEqual(redacted["items"][0]["name"], "ok")

    def test_cli_exposes_reservation_and_result_commands_but_not_publish(self):
        parser = build_parser()
        self.assertEqual(
            parser.parse_args(["reserve-approved-action", "request.json", "grant.json", "state"]).command,
            "reserve-approved-action",
        )
        self.assertEqual(
            parser.parse_args([
                "record-execution-result",
                "reservation.json",
                "audit.jsonl",
                "--status",
                "failed",
                "--attempt",
                "1",
            ]).command,
            "record-execution-result",
        )
        with self.assertRaises(SystemExit):
            parser.parse_args(["publish"])


if __name__ == "__main__":
    unittest.main()
