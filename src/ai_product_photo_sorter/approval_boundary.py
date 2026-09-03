from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SENSITIVE_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _request_id(action: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(f"{action}\n{_canonical(payload)}".encode("utf-8")).hexdigest()[:16]
    return f"apr_{digest}"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _reject_embedded_secrets(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if any(fragment in normalized for fragment in SENSITIVE_FRAGMENTS):
                raise ValueError(f"Approval payload must not embed credential-like fields: {path}.{key}")
            _reject_embedded_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_embedded_secrets(item, f"{path}[{index}]")


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
    _reject_embedded_secrets(payload)
    request = ApprovalRequest(
        request_id=_request_id(action, payload),
        action=action,
        payload=payload,
        created_at=_now(),
    )
    path = Path(output).expanduser().resolve()
    _atomic_json(path, request.to_dict())
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
    payload = request.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Approval request payload must be an object")
    _reject_embedded_secrets(payload)
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", "")).strip()
    if not request_id or not action:
        raise ValueError("Approval request is missing request_id or action")
    if _request_id(action, payload) != request_id:
        raise ValueError("Approval request id does not match action and payload")
    expected = f"APPROVE {request_id}"
    if confirmation != expected:
        raise ValueError(f"Explicit confirmation required: {expected}")
    grant = {
        "schema_version": SCHEMA_VERSION,
        "mode": "approval_grant",
        "request_id": request_id,
        "action": action,
        "payload_sha256": hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
        "approved_at": _now(),
        "human_confirmation": expected,
        "single_use": True,
        "external_action_performed": False,
    }
    target = Path(grant_path).expanduser().resolve()
    _atomic_json(target, grant)
    return target


def validate_grant(request_path: str | Path, grant_path: str | Path) -> dict[str, Any]:
    request = json.loads(Path(request_path).expanduser().resolve().read_text(encoding="utf-8"))
    grant = json.loads(Path(grant_path).expanduser().resolve().read_text(encoding="utf-8"))
    if request.get("mode") != "approval_request" or grant.get("mode") != "approval_grant":
        raise ValueError("Invalid approval request/grant pair")
    payload = request.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Approval request payload must be an object")
    _reject_embedded_secrets(payload)
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", "")).strip()
    if _request_id(action, payload) != request_id:
        raise ValueError("Approval request id does not match action and payload")
    if request_id != grant.get("request_id"):
        raise ValueError("Approval grant does not match request id")
    if action != str(grant.get("action", "")):
        raise ValueError("Approval grant does not match request action")
    payload_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    if payload_hash != grant.get("payload_sha256"):
        raise ValueError("Approval grant does not match request payload")
    if grant.get("single_use") is not True:
        raise ValueError("Approval grant must be single-use")
    return {
        "request_id": request_id,
        "action": action,
        "approved": True,
        "single_use": True,
        "external_action_performed": False,
    }
