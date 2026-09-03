from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _request_id(action: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(f"{action}\n{_canonical(payload)}".encode("utf-8")).hexdigest()[:16]
    return f"apr_{digest}"


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    action: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": "approval_request",
            "request_id": self.request_id,
            "action": self.action,
            "payload": self.payload,
            "created_at": self.created_at,
            "agent_can_approve": False,
        }


def create_approval_request(action: str, payload: dict[str, Any], output: str | Path) -> Path:
    action = action.strip()
    if not action:
        raise ValueError("action cannot be empty")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    request = ApprovalRequest(
        request_id=_request_id(action, payload),
        action=action,
        payload=payload,
        created_at=_now(),
    )
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(request.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def approve_request(request_path: str | Path, grant_path: str | Path, confirmation: str) -> Path:
    source = Path(request_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Approval request does not exist: {source}")
    try:
        request = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read approval request {source}: {exc}") from exc
    if not isinstance(request, dict) or request.get("mode") != "approval_request":
        raise ValueError("File is not a Product Sorter approval request")
    request_id = str(request.get("request_id", ""))
    expected = f"APPROVE {request_id}"
    if confirmation != expected:
        raise ValueError(f"Explicit confirmation required: {expected}")
    grant = {
        "schema_version": SCHEMA_VERSION,
        "mode": "approval_grant",
        "request_id": request_id,
        "action": request.get("action"),
        "payload_sha256": hashlib.sha256(_canonical(dict(request.get("payload", {}))).encode("utf-8")).hexdigest(),
        "approved_at": _now(),
        "human_confirmation": expected,
        "single_use": True,
        "external_action_performed": False,
    }
    target = Path(grant_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(grant, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def validate_grant(request_path: str | Path, grant_path: str | Path) -> dict[str, Any]:
    request = json.loads(Path(request_path).expanduser().resolve().read_text(encoding="utf-8"))
    grant = json.loads(Path(grant_path).expanduser().resolve().read_text(encoding="utf-8"))
    if request.get("mode") != "approval_request" or grant.get("mode") != "approval_grant":
        raise ValueError("Invalid approval request/grant pair")
    if request.get("request_id") != grant.get("request_id"):
        raise ValueError("Approval grant does not match request id")
    payload_hash = hashlib.sha256(_canonical(dict(request.get("payload", {}))).encode("utf-8")).hexdigest()
    if payload_hash != grant.get("payload_sha256"):
        raise ValueError("Approval grant does not match request payload")
    return {
        "request_id": request.get("request_id"),
        "action": request.get("action"),
        "approved": True,
        "single_use": True,
        "external_action_performed": False,
    }
