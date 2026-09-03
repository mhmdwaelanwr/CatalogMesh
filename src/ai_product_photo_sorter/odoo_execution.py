from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .execution_control import append_execution_audit, idempotency_key, record_execution_result, redact_secrets

ACTION = "odoo.apply_products"
STATE_MODE = "odoo_execution_state"
PLAN_MODE = "catalog_connector_write_plan"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path, expected_mode: str | None = None) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"File does not exist: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON file {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {source}")
    if expected_mode and payload.get("mode") != expected_mode:
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


def _normalize_base_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Odoo base_url must be a credential-free HTTPS origin")
    if parsed.path not in {"", "/"}:
        raise ValueError("Odoo base_url must not include an application path")
    return f"https://{parsed.netloc.lower()}"


class OdooClient:
    def __init__(self, base_url: str, database: str, username: str, api_key: str, *, timeout: float = 45.0):
        self.base_url = _normalize_base_url(base_url)
        self.database = database.strip()
        self.username = username.strip()
        self.api_key = api_key
        self.timeout = timeout
        self._uid: int | None = None
        if not all((self.database, self.username, self.api_key)):
            raise ValueError("Odoo connector credentials cannot be blank")

    def _rpc(self, service: str, method: str, args: list[Any]) -> Any:
        request = urllib.request.Request(
            f"{self.base_url}/jsonrpc",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"service": service, "method": method, "args": args}, "id": 1}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError(f"Odoo request failed: {exc}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError(f"Odoo RPC error: {payload['error'].get('message') or payload['error']}")
        return payload.get("result") if isinstance(payload, dict) else None

    def uid(self) -> int:
        if self._uid is None:
            result = self._rpc("common", "authenticate", [self.database, self.username, self.api_key, {}])
            try:
                self._uid = int(result)
            except (TypeError, ValueError) as exc:
                raise ValueError("Odoo authentication failed") from exc
            if self._uid <= 0:
                raise ValueError("Odoo authentication failed")
        return self._uid

    def execute_kw(self, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None) -> Any:
        return self._rpc("object", "execute_kw", [self.database, self.uid(), self.api_key, model, method, args, kwargs or {}])

    def find_product(self, default_code: str) -> dict[str, Any] | None:
        ids = self.execute_kw("product.product", "search", [[["default_code", "=", default_code]]], {"limit": 2}) or []
        if len(ids) > 1:
            raise ValueError(f"Odoo default_code is not unique: {default_code}")
        if not ids:
            return None
        rows = self.execute_kw("product.product", "read", [ids, ["id", "default_code", "name", "barcode", "active"]], {}) or []
        return dict(rows[0]) if rows else None

    def write_product(self, product_id: int, values: dict[str, Any]) -> bool:
        return bool(self.execute_kw("product.product", "write", [[product_id], values], {}))


def _odoo_values(record: dict[str, Any]) -> dict[str, Any]:
    identity = str(record.get("identity", "")).strip()
    fields = record.get("fields", {})
    if not identity or not isinstance(fields, dict):
        raise ValueError("Odoo plan record requires identity and mapped fields")
    allowed = {"default_code", "name", "barcode", "active"}
    values: dict[str, Any] = {}
    for target, raw in fields.items():
        name = str(target).strip()
        if name not in allowed:
            raise ValueError(f"Unsupported Odoo product target field: {name}")
        if name == "default_code":
            if str(raw).strip() != identity:
                raise ValueError(f"Odoo default_code mapping does not match record identity: {identity}")
            continue
        if name == "active":
            normalized = raw if isinstance(raw, bool) else str(raw).strip().lower()
            if normalized in (True, "true", "1", "yes"):
                values[name] = True
            elif normalized in (False, "false", "0", "no"):
                values[name] = False
            else:
                raise ValueError(f"Odoo active must be boolean-like for {identity}")
        else:
            values[name] = str(raw).strip()
    if not values:
        raise ValueError(f"Odoo record {identity} has no writable fields")
    return values


def _validated_inputs(request_path: str | Path, reservation_path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    request = _read_json(request_path, "approval_request")
    reservation = _read_json(reservation_path, "execution_reservation")
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", ""))
    payload = request.get("payload", {})
    if action != ACTION:
        raise ValueError(f"Odoo execution accepts only action {ACTION}")
    if not isinstance(payload, dict):
        raise ValueError("Approval request payload must be an object")
    if request_id != str(reservation.get("request_id", "")) or action != str(reservation.get("action", "")):
        raise ValueError("Execution reservation does not match approval request")
    if idempotency_key(request_id, action, payload) != reservation.get("idempotency_key"):
        raise ValueError("Execution reservation idempotency key does not match approval request")
    if reservation.get("status") != "reserved":
        raise ValueError(f"Execution reservation is not available: status={reservation.get('status')}")

    plan_path = Path(str(payload.get("plan_path", ""))).expanduser().resolve()
    plan = _read_json(plan_path, PLAN_MODE)
    if plan.get("connector_kind") != "erp" or str(plan.get("entity", "")).lower() not in {"product", "products"}:
        raise ValueError("Odoo execution accepts only ERP product write plans")
    if int(plan.get("network_calls_performed", 0)) != 0 or bool(plan.get("external_action_performed")):
        raise ValueError("Odoo execution requires an untouched zero-network connector plan")
    approved_plan_id = str(payload.get("plan_id", "")).strip()
    if not approved_plan_id or approved_plan_id != str(plan.get("plan_id", "")):
        raise ValueError("Approved Odoo plan_id does not match connector plan")
    base_url = _normalize_base_url(str(payload.get("base_url", "")))
    database = str(payload.get("database", "")).strip()
    if not database:
        raise ValueError("Odoo approval payload requires database")

    records = plan.get("records", [])
    if not isinstance(records, list) or not records:
        raise ValueError("Odoo connector plan contains no records")
    prepared, seen = [], set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Odoo connector plan records must be objects")
        identity = str(item.get("identity", "")).strip()
        if identity in seen:
            raise ValueError(f"Odoo connector plan contains duplicate identity: {identity}")
        seen.add(identity)
        prepared.append({"record": item, "values": _odoo_values(item)})
    approved = {"plan_path": str(plan_path), "plan_id": approved_plan_id, "base_url": base_url, "database": database, "prepared": prepared}
    return request, reservation, approved, plan, Path(reservation_path).expanduser().resolve()


def execute_odoo_products(request_path: str | Path, reservation_path: str | Path, client: OdooClient, *, audit_path: str | Path | None = None, state_path: str | Path | None = None) -> dict[str, Any]:
    _, reservation, approved, plan, reservation_file = _validated_inputs(request_path, reservation_path)
    if approved["base_url"] != client.base_url or approved["database"] != client.database:
        raise ValueError("Approved Odoo origin/database does not match connector client")
    audit = Path(audit_path).expanduser().resolve() if audit_path else reservation_file.parent.parent / "execution_audit.jsonl"
    state_file = Path(state_path).expanduser().resolve() if state_path else reservation_file.parent.parent / "odoo_execution_state.json"

    targets = []
    for prepared in approved["prepared"]:
        identity = str(prepared["record"]["identity"])
        before = client.find_product(identity)
        if before is None:
            raise ValueError(f"Odoo product does not already exist: {identity}; creation is out of scope")
        targets.append({"identity": identity, "before": before, "values": prepared["values"]})

    reservation.update({"status": "consumed", "consumed_at": _now(), "connector": "odoo", "external_action_performed": False})
    _atomic_json(reservation_file, reservation)
    append_execution_audit(audit, {"event": "reservation_consumed", "request_id": reservation["request_id"], "action": ACTION, "idempotency_key": reservation["idempotency_key"], "status": "consumed", "external_action_performed": False, "payload": redact_secrets({"plan_id": approved["plan_id"], "base_url": approved["base_url"], "database": approved["database"]})})

    state: dict[str, Any] = {"schema_version": 1, "mode": STATE_MODE, "created_at": _now(), "updated_at": _now(), "request_id": reservation["request_id"], "idempotency_key": reservation["idempotency_key"], "plan_id": approved["plan_id"], "profile_id": plan.get("profile_id"), "base_url": approved["base_url"], "database": approved["database"], "status": "ready_to_apply", "records": [{"identity": t["identity"], "product_id": t["before"]["id"], "before": t["before"], "write_status": "pending"} for t in targets], "automatic_rollback_performed": False}
    _atomic_json(state_file, state)

    applied = 0
    try:
        for index, target in enumerate(targets):
            if not client.write_product(int(target["before"]["id"]), target["values"]):
                raise ValueError(f"Odoo write returned false for {target['identity']}")
            applied += 1
            state["records"][index].update({"write_status": "applied", "applied_at": _now()})
            state["updated_at"] = _now()
            _atomic_json(state_file, state)
        state.update({"status": "succeeded", "completed_at": _now()})
        state["updated_at"] = state["completed_at"]
        _atomic_json(state_file, state)
        result = record_execution_result(reservation_file, audit, status="succeeded", attempt=1, details={"connector": "odoo", "operation": "apply_products", "plan_id": approved["plan_id"], "base_url": approved["base_url"], "database": approved["database"], "records_applied": applied, "state_path": str(state_file), "automatic_rollback_performed": False}, external_action_performed=True)
        reservation.update({"status": "succeeded", "completed_at": _now(), "external_action_performed": True, "attempts": 1, "result_state_path": str(state_file)})
        _atomic_json(reservation_file, reservation)
        return result | {"state_path": str(state_file), "records_applied": applied, "automatic_rollback_performed": False}
    except Exception as exc:
        performed = applied > 0
        state.update({"status": "failed", "completed_at": _now(), "last_error": str(exc), "reconciliation_required": performed})
        state["updated_at"] = state["completed_at"]
        _atomic_json(state_file, state)
        record_execution_result(reservation_file, audit, status="failed", attempt=1, details={"connector": "odoo", "operation": "apply_products", "plan_id": approved["plan_id"], "base_url": approved["base_url"], "database": approved["database"], "error": str(exc), "state_path": str(state_file), "reconciliation_required": performed, "automatic_rollback_performed": False}, external_action_performed=performed)
        reservation.update({"status": "failed", "completed_at": _now(), "external_action_performed": performed, "attempts": 1, "last_error": str(exc), "result_state_path": str(state_file)})
        _atomic_json(reservation_file, reservation)
        raise ValueError(f"Approved Odoo product execution failed: {exc}") from exc


def reconcile_odoo_execution(state_path: str | Path, client: OdooClient) -> dict[str, Any]:
    state = _read_json(state_path, STATE_MODE)
    if _normalize_base_url(str(state.get("base_url", ""))) != client.base_url or str(state.get("database", "")) != client.database:
        raise ValueError("Odoo execution state belongs to a different origin/database")
    records = []
    for item in state.get("records", []):
        identity = str(item.get("identity", ""))
        current = client.find_product(identity)
        records.append({"identity": identity, "exists_now": current is not None, "changed_from_before": current != item.get("before"), "write_status": item.get("write_status")})
    return {"mode": "odoo_reconciliation_report", "state_path": str(Path(state_path).expanduser().resolve()), "records": records, "network_writes_performed": 0, "external_action_performed": False}
