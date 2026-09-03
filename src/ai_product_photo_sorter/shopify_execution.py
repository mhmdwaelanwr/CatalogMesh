from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .execution_control import append_execution_audit, idempotency_key, record_execution_result, redact_secrets
from .shopify_publishing import ShopifyClient, stage_drafts

ACTION = "shopify.stage_drafts"


def _now() -> str:
    from datetime import datetime, timezone

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
        if temp.exists():
            temp.unlink(missing_ok=True)


def _validated_inputs(request_path: str | Path, reservation_path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request = _read_json(request_path, "approval_request")
    reservation = _read_json(reservation_path, "execution_reservation")
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", ""))
    payload = request.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Approval request payload must be an object")
    if action != ACTION:
        raise ValueError(f"Shopify automation accepts only action {ACTION}")
    if request_id != str(reservation.get("request_id", "")) or action != str(reservation.get("action", "")):
        raise ValueError("Execution reservation does not match approval request")
    expected_key = idempotency_key(request_id, action, payload)
    if expected_key != reservation.get("idempotency_key"):
        raise ValueError("Execution reservation idempotency key does not match approval request")
    if reservation.get("status") != "reserved":
        raise ValueError(f"Execution reservation is not available: status={reservation.get('status')}")
    export_manifest = str(payload.get("export_manifest", "")).strip()
    if not export_manifest:
        raise ValueError("Shopify stage approval payload requires export_manifest")
    normalized = {
        "export_manifest": str(Path(export_manifest).expanduser().resolve()),
        "output_dir": str(Path(str(payload["output_dir"])).expanduser().resolve()) if payload.get("output_dir") else None,
        "upload_images": bool(payload.get("upload_images", True)),
        "store_domain": str(payload.get("store_domain", "")).strip().lower(),
    }
    return request, reservation, normalized


def _is_retryable(exc: Exception) -> bool:
    text = str(exc)
    return text.startswith("Shopify request failed:") or text.startswith("Shopify staged image upload failed")


def execute_shopify_stage(
    request_path: str | Path,
    reservation_path: str | Path,
    client: ShopifyClient,
    *,
    audit_path: str | Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    request, reservation, payload = _validated_inputs(request_path, reservation_path)
    reservation_file = Path(reservation_path).expanduser().resolve()
    audit = Path(audit_path).expanduser().resolve() if audit_path else reservation_file.parent.parent / "execution_audit.jsonl"

    if payload["store_domain"] and payload["store_domain"] != client.store_domain:
        raise ValueError("Approved Shopify store domain does not match connector client")

    retry_policy = reservation.get("retry_policy", {})
    max_attempts = int(retry_policy.get("max_attempts", 1))
    base_delay = float(retry_policy.get("base_delay_seconds", 0.0))
    max_delay = float(retry_policy.get("max_delay_seconds", base_delay))
    if max_attempts < 1 or max_attempts > 10:
        raise ValueError("Reservation retry policy max_attempts must be between 1 and 10")

    reservation["status"] = "consumed"
    reservation["consumed_at"] = _now()
    reservation["connector"] = "shopify"
    reservation["external_action_performed"] = False
    _atomic_json(reservation_file, reservation)
    append_execution_audit(
        audit,
        {
            "event": "reservation_consumed",
            "request_id": reservation["request_id"],
            "action": ACTION,
            "idempotency_key": reservation["idempotency_key"],
            "status": "consumed",
            "external_action_performed": False,
            "payload": redact_secrets(payload),
        },
    )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            state, state_path = stage_drafts(
                Path(payload["export_manifest"]),
                client,
                output_dir=Path(payload["output_dir"]) if payload["output_dir"] else None,
                upload_images=payload["upload_images"],
            )
            result = record_execution_result(
                reservation_file,
                audit,
                status="succeeded",
                attempt=attempt,
                details={
                    "connector": "shopify",
                    "operation": "stage_drafts",
                    "idempotency_key": reservation["idempotency_key"],
                    "state_path": str(state_path),
                    "products": len(state.get("products", {})),
                    "remote_status": "DRAFT",
                    "published": False,
                },
                external_action_performed=True,
            )
            reservation["status"] = "succeeded"
            reservation["completed_at"] = _now()
            reservation["external_action_performed"] = True
            reservation["attempts"] = attempt
            reservation["result_state_path"] = str(state_path)
            _atomic_json(reservation_file, reservation)
            return result | {
                "reservation": str(reservation_file),
                "state_path": str(state_path),
                "published": False,
                "remote_status": "DRAFT",
            }
        except Exception as exc:  # connector boundary must always finalize local state
            last_error = exc
            retryable = _is_retryable(exc)
            record_execution_result(
                reservation_file,
                audit,
                status="failed",
                attempt=attempt,
                details={
                    "connector": "shopify",
                    "operation": "stage_drafts",
                    "idempotency_key": reservation["idempotency_key"],
                    "retryable": retryable,
                    "error": str(exc),
                },
                external_action_performed=True,
            )
            if not retryable or attempt >= max_attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if delay > 0:
                sleep(delay)

    reservation["status"] = "failed"
    reservation["completed_at"] = _now()
    reservation["external_action_performed"] = True
    reservation["attempts"] = attempt
    reservation["last_error"] = str(last_error)
    _atomic_json(reservation_file, reservation)
    raise ValueError(f"Approved Shopify draft staging failed after {attempt} attempt(s): {last_error}") from last_error
