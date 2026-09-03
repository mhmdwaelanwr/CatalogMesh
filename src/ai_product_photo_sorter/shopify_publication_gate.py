from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .execution_control import append_execution_audit, idempotency_key, record_execution_result, redact_secrets
from .shopify_publishing import ShopifyClient, publish_staged, rollback_publication

PUBLISH_ACTION = "shopify.publish_staged"
ROLLBACK_ACTION = "shopify.rollback_publication"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path, expected_mode: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"File does not exist: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON file {source}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != expected_mode:
        raise ValueError(f"File is not a Product Sorter {expected_mode}")
    return payload


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False)
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


def _validated(request_path: str | Path, reservation_path: str | Path, expected_action: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    request = _read_json(request_path, "approval_request")
    reservation = _read_json(reservation_path, "execution_reservation")
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", ""))
    payload = request.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Approval request payload must be an object")
    if action != expected_action:
        raise ValueError(f"Publication gate accepts only action {expected_action}")
    if request_id != str(reservation.get("request_id", "")) or action != str(reservation.get("action", "")):
        raise ValueError("Execution reservation does not match approval request")
    if idempotency_key(request_id, action, payload) != reservation.get("idempotency_key"):
        raise ValueError("Execution reservation idempotency key does not match approval request")
    if reservation.get("status") != "reserved":
        raise ValueError(f"Execution reservation is not available: status={reservation.get('status')}")
    state_path = Path(str(payload.get("state_path", ""))).expanduser().resolve()
    if not state_path.is_file():
        raise ValueError("Approved Shopify publication payload requires an existing state_path")
    normalized = {
        "state_path": str(state_path),
        "store_domain": str(payload.get("store_domain", "")).strip().lower(),
        "publication_id": str(payload.get("publication_id", "")).strip(),
    }
    return request, reservation, normalized, Path(reservation_path).expanduser().resolve()


def _consume(reservation_file: Path, reservation: dict[str, Any], audit: Path, action: str, payload: dict[str, Any]) -> None:
    reservation["status"] = "consumed"
    reservation["consumed_at"] = _now()
    reservation["connector"] = "shopify"
    reservation["external_action_performed"] = False
    _atomic_json(reservation_file, reservation)
    append_execution_audit(audit, {"event": "reservation_consumed", "request_id": reservation["request_id"], "action": action, "idempotency_key": reservation["idempotency_key"], "status": "consumed", "external_action_performed": False, "payload": redact_secrets(payload)})


def execute_shopify_publish(request_path: str | Path, reservation_path: str | Path, client: ShopifyClient, *, audit_path: str | Path | None = None) -> dict[str, Any]:
    _, reservation, payload, reservation_file = _validated(request_path, reservation_path, PUBLISH_ACTION)
    if payload["store_domain"] and payload["store_domain"] != client.store_domain:
        raise ValueError("Approved Shopify store domain does not match connector client")
    if not payload["publication_id"].startswith("gid://shopify/Publication/"):
        raise ValueError("Approved publication payload requires a valid Shopify publication GID")
    audit = Path(audit_path).expanduser().resolve() if audit_path else reservation_file.parent.parent / "execution_audit.jsonl"
    _consume(reservation_file, reservation, audit, PUBLISH_ACTION, payload)
    try:
        state, state_path = publish_staged(Path(payload["state_path"]), client, publication_id=payload["publication_id"], confirmation="PUBLISH")
        result = record_execution_result(reservation_file, audit, status="succeeded", attempt=1, details={"connector": "shopify", "operation": "publish_staged", "idempotency_key": reservation["idempotency_key"], "state_path": str(state_path), "published_products": sum(bool(item.get("published")) for item in state.get("products", {}).values())}, external_action_performed=True)
        reservation.update({"status": "succeeded", "completed_at": _now(), "external_action_performed": True, "attempts": 1})
        _atomic_json(reservation_file, reservation)
        return result | {"reservation": str(reservation_file), "state_path": str(state_path), "published": True}
    except Exception as exc:
        record_execution_result(reservation_file, audit, status="failed", attempt=1, details={"connector": "shopify", "operation": "publish_staged", "idempotency_key": reservation["idempotency_key"], "error": str(exc)}, external_action_performed=True)
        reservation.update({"status": "failed", "completed_at": _now(), "external_action_performed": True, "attempts": 1, "last_error": str(exc)})
        _atomic_json(reservation_file, reservation)
        raise ValueError(f"Approved Shopify publication failed: {exc}") from exc


def execute_shopify_rollback(request_path: str | Path, reservation_path: str | Path, client: ShopifyClient, *, audit_path: str | Path | None = None) -> dict[str, Any]:
    _, reservation, payload, reservation_file = _validated(request_path, reservation_path, ROLLBACK_ACTION)
    if payload["store_domain"] and payload["store_domain"] != client.store_domain:
        raise ValueError("Approved Shopify store domain does not match connector client")
    audit = Path(audit_path).expanduser().resolve() if audit_path else reservation_file.parent.parent / "execution_audit.jsonl"
    _consume(reservation_file, reservation, audit, ROLLBACK_ACTION, payload)
    try:
        state, state_path = rollback_publication(Path(payload["state_path"]), client, confirmation="UNPUBLISH")
        result = record_execution_result(reservation_file, audit, status="succeeded", attempt=1, details={"connector": "shopify", "operation": "rollback_publication", "idempotency_key": reservation["idempotency_key"], "state_path": str(state_path), "published_products_remaining": sum(bool(item.get("published")) for item in state.get("products", {}).values())}, external_action_performed=True)
        reservation.update({"status": "succeeded", "completed_at": _now(), "external_action_performed": True, "attempts": 1})
        _atomic_json(reservation_file, reservation)
        return result | {"reservation": str(reservation_file), "state_path": str(state_path), "rolled_back": True}
    except Exception as exc:
        record_execution_result(reservation_file, audit, status="failed", attempt=1, details={"connector": "shopify", "operation": "rollback_publication", "idempotency_key": reservation["idempotency_key"], "error": str(exc)}, external_action_performed=True)
        reservation.update({"status": "failed", "completed_at": _now(), "external_action_performed": True, "attempts": 1, "last_error": str(exc)})
        _atomic_json(reservation_file, reservation)
        raise ValueError(f"Approved Shopify rollback failed: {exc}") from exc
