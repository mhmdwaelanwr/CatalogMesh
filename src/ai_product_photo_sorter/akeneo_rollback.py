from __future__ import annotations

from pathlib import Path
from typing import Any

from .akeneo_execution import (
    AkeneoClient,
    STATE_MODE,
    _atomic_json,
    _fingerprint,
    _normalize_base_url,
    _now,
    _read_json,
)
from .execution_control import idempotency_key, record_execution_result

ACTION = "akeneo.rollback_products"


def _validated_inputs(
    request_path: str | Path,
    reservation_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    request = _read_json(request_path, "approval_request")
    reservation = _read_json(reservation_path, "execution_reservation")
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", ""))
    payload = request.get("payload", {})
    if action != ACTION:
        raise ValueError(f"Akeneo rollback accepts only action {ACTION}")
    if not isinstance(payload, dict):
        raise ValueError("Approval request payload must be an object")
    if request_id != str(reservation.get("request_id", "")) or action != str(reservation.get("action", "")):
        raise ValueError("Execution reservation does not match rollback approval request")
    if idempotency_key(request_id, action, payload) != reservation.get("idempotency_key"):
        raise ValueError("Execution reservation idempotency key does not match rollback approval request")
    if reservation.get("status") != "reserved":
        raise ValueError(f"Execution reservation is not available: status={reservation.get('status')}")

    state_path = Path(str(payload.get("state_path", ""))).expanduser().resolve()
    state = _read_json(state_path, STATE_MODE)
    approved_plan_id = str(payload.get("plan_id", "")).strip()
    if not approved_plan_id or approved_plan_id != str(state.get("plan_id", "")):
        raise ValueError("Approved rollback plan_id does not match execution state")
    base_url = _normalize_base_url(str(payload.get("base_url", "")))
    if base_url != _normalize_base_url(str(state.get("base_url", ""))):
        raise ValueError("Approved rollback base_url does not match execution state")
    if bool(state.get("automatic_rollback_performed")):
        raise ValueError("Execution state already records a rollback")

    targets: list[dict[str, Any]] = []
    for item in state.get("records", []):
        if not isinstance(item, dict) or item.get("write_status") != "applied":
            continue
        if not item.get("before_exists"):
            raise ValueError(
                "Rollback cannot safely restore a product that did not exist before execution; "
                "creation deletion requires a separate explicitly approved action"
            )
        before = item.get("before")
        identity = str(item.get("identity", "")).strip()
        if not identity or not isinstance(before, dict):
            raise ValueError("Rollback state is missing a restorable pre-write product snapshot")
        targets.append({"identity": identity, "before": before})
    if not targets:
        raise ValueError("Execution state contains no safely restorable applied products")

    expected = payload.get("expected_current_fingerprints")
    if not isinstance(expected, dict):
        raise ValueError(
            "Akeneo rollback approval requires expected_current_fingerprints from a fresh read-only reconciliation"
        )
    identities = {target["identity"] for target in targets}
    if set(expected) != identities:
        raise ValueError("Rollback fingerprint set must exactly match every safely restorable applied product")
    normalized_expected: dict[str, str] = {}
    for identity in sorted(identities):
        value = expected.get(identity)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"Rollback fingerprint for {identity} must be a SHA-256 hex string")
        lowered = value.lower()
        if any(char not in "0123456789abcdef" for char in lowered):
            raise ValueError(f"Rollback fingerprint for {identity} must be a SHA-256 hex string")
        normalized_expected[identity] = lowered

    return (
        request,
        reservation,
        {
            "state_path": state_path,
            "state": state,
            "plan_id": approved_plan_id,
            "base_url": base_url,
            "targets": targets,
            "expected_current_fingerprints": normalized_expected,
        },
        Path(reservation_path).expanduser().resolve(),
    )


def execute_akeneo_rollback(
    request_path: str | Path,
    reservation_path: str | Path,
    client: AkeneoClient,
    *,
    audit_path: str | Path | None = None,
) -> dict[str, Any]:
    _, reservation, approved, reservation_file = _validated_inputs(request_path, reservation_path)
    if approved["base_url"] != client.base_url:
        raise ValueError("Approved Akeneo rollback base_url does not match connector client")
    audit = Path(audit_path).expanduser().resolve() if audit_path else reservation_file.parent.parent / "execution_audit.jsonl"

    # The fresh human approval is bound to the exact current remote fingerprints. Any
    # remote drift after reconciliation/approval blocks rollback before consuming the
    # single-use reservation and before any PATCH occurs.
    for target in approved["targets"]:
        identity = target["identity"]
        current = client.get_product(identity)
        if current is None:
            raise ValueError(f"Rollback target no longer exists: {identity}")
        actual = _fingerprint(current)
        expected = approved["expected_current_fingerprints"][identity]
        if actual != expected:
            raise ValueError(
                f"Rollback blocked because remote product drifted after reconciliation: {identity}"
            )

    reservation["status"] = "consumed"
    reservation["consumed_at"] = _now()
    reservation["connector"] = "akeneo"
    reservation["external_action_performed"] = False
    _atomic_json(reservation_file, reservation)

    restored = 0
    state = approved["state"]
    try:
        for target in approved["targets"]:
            before = target["before"]
            payload = {
                key: value
                for key, value in before.items()
                if key
                in {
                    "enabled",
                    "family",
                    "categories",
                    "groups",
                    "parent",
                    "values",
                    "associations",
                    "quantified_associations",
                }
            }
            if not payload:
                raise ValueError(f"Stored snapshot has no restorable Akeneo fields: {target['identity']}")
            client.patch_product(target["identity"], payload)
            restored += 1
        state["rollback_status"] = "succeeded"
        state["rollback_completed_at"] = _now()
        state["rollback_request_id"] = reservation["request_id"]
        state["rollback_records_restored"] = restored
        state["automatic_rollback_performed"] = False
        _atomic_json(approved["state_path"], state)
        result = record_execution_result(
            reservation_file,
            audit,
            status="succeeded",
            attempt=1,
            details={
                "connector": "akeneo",
                "operation": "rollback_products",
                "plan_id": approved["plan_id"],
                "base_url": approved["base_url"],
                "records_restored": restored,
                "state_path": str(approved["state_path"]),
                "remote_fingerprints_verified": True,
                "automatic_rollback_performed": False,
            },
            external_action_performed=True,
        )
        reservation.update(
            {
                "status": "succeeded",
                "completed_at": _now(),
                "external_action_performed": True,
                "attempts": 1,
                "result_state_path": str(approved["state_path"]),
            }
        )
        _atomic_json(reservation_file, reservation)
        return result | {"records_restored": restored, "state_path": str(approved["state_path"])}
    except Exception as exc:
        state["rollback_status"] = "failed"
        state["rollback_completed_at"] = _now()
        state["rollback_request_id"] = reservation["request_id"]
        state["rollback_records_restored"] = restored
        state["rollback_reconciliation_required"] = restored > 0
        state["rollback_last_error"] = str(exc)
        _atomic_json(approved["state_path"], state)
        record_execution_result(
            reservation_file,
            audit,
            status="failed",
            attempt=1,
            details={
                "connector": "akeneo",
                "operation": "rollback_products",
                "plan_id": approved["plan_id"],
                "base_url": approved["base_url"],
                "records_restored": restored,
                "state_path": str(approved["state_path"]),
                "reconciliation_required": restored > 0,
                "error": str(exc),
            },
            external_action_performed=restored > 0,
        )
        reservation.update(
            {
                "status": "failed",
                "completed_at": _now(),
                "external_action_performed": restored > 0,
                "attempts": 1,
                "last_error": str(exc),
                "result_state_path": str(approved["state_path"]),
            }
        )
        _atomic_json(reservation_file, reservation)
        raise ValueError(f"Approved Akeneo rollback failed: {exc}") from exc
