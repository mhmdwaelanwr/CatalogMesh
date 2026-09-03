from __future__ import annotations

import base64
import hashlib
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

ACTION = "akeneo.apply_products"
STATE_MODE = "akeneo_execution_state"
PLAN_MODE = "catalog_connector_write_plan"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


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
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Akeneo base_url must be a credential-free HTTPS origin")
    if parsed.path not in {"", "/"}:
        raise ValueError("Akeneo base_url must not include an API path")
    return f"https://{parsed.netloc.lower()}"


class AkeneoClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, username: str, password: str, *, timeout: float = 45.0):
        self.base_url = _normalize_base_url(base_url)
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.username = username.strip()
        self.password = password
        self.timeout = timeout
        if not all((self.client_id, self.client_secret, self.username, self.password)):
            raise ValueError("Akeneo connector credentials cannot be blank")
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        body = urllib.parse.urlencode({"grant_type": "password", "username": self.username, "password": self.password}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/oauth/v1/token",
            data=body,
            method="POST",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError(f"Akeneo authentication failed: {exc}") from exc
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise ValueError("Akeneo authentication response did not include access_token")
        self._access_token = token
        return token

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, *, allow_not_found: bool = False) -> dict[str, Any] | None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                payload = json.loads(raw.decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
        except urllib.error.HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return None
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
            except Exception:
                detail = ""
            raise ValueError(f"Akeneo request failed: HTTP {exc.code} {detail}".strip()) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError(f"Akeneo request failed: {exc}") from exc

    def get_product(self, identifier: str) -> dict[str, Any] | None:
        code = urllib.parse.quote(identifier, safe="")
        return self._request("GET", f"/api/rest/v1/products/{code}", allow_not_found=True)

    def patch_product(self, identifier: str, payload: dict[str, Any]) -> dict[str, Any]:
        code = urllib.parse.quote(identifier, safe="")
        return dict(self._request("PATCH", f"/api/rest/v1/products/{code}", payload) or {})


def _akeneo_payload(record: dict[str, Any]) -> dict[str, Any]:
    identity = str(record.get("identity", "")).strip()
    fields = record.get("fields", {})
    if not identity or not isinstance(fields, dict):
        raise ValueError("Akeneo plan record requires identity and mapped fields")
    values: dict[str, list[dict[str, Any]]] = {}
    for target, raw in fields.items():
        name = str(target).strip()
        value = str(raw)
        if name in {"identifier", "code"}:
            if value.strip() and value.strip() != identity:
                raise ValueError(f"Akeneo identifier mapping does not match record identity: {identity}")
            continue
        if not name.startswith("values.") or len(name) <= len("values."):
            raise ValueError(f"Unsupported Akeneo target field '{name}'; use identifier/code or values.<attribute_code>")
        attribute = name.split(".", 1)[1]
        if not attribute.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid Akeneo attribute code: {attribute}")
        values[attribute] = [{"locale": None, "scope": None, "data": value}]
    if not values:
        raise ValueError(f"Akeneo record {identity} has no writable values.<attribute_code> fields")
    return {"identifier": identity, "values": values}


def _validated_inputs(request_path: str | Path, reservation_path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    request = _read_json(request_path, "approval_request")
    reservation = _read_json(reservation_path, "execution_reservation")
    request_id = str(request.get("request_id", ""))
    action = str(request.get("action", ""))
    payload = request.get("payload", {})
    if action != ACTION:
        raise ValueError(f"Akeneo execution accepts only action {ACTION}")
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
    if plan.get("connector_kind") != "pim" or str(plan.get("entity", "")).lower() not in {"product", "products"}:
        raise ValueError("Akeneo execution accepts only PIM product write plans")
    if int(plan.get("network_calls_performed", 0)) != 0 or bool(plan.get("external_action_performed")):
        raise ValueError("Akeneo execution requires an untouched zero-network connector plan")
    approved_plan_id = str(payload.get("plan_id", "")).strip()
    if not approved_plan_id or approved_plan_id != str(plan.get("plan_id", "")):
        raise ValueError("Approved Akeneo plan_id does not match connector plan")
    base_url = _normalize_base_url(str(payload.get("base_url", "")))
    records = plan.get("records", [])
    if not isinstance(records, list) or not records:
        raise ValueError("Akeneo connector plan contains no records")
    prepared = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Akeneo connector plan records must be objects")
        prepared.append({"record": item, "payload": _akeneo_payload(item)})
    normalized = {"plan_path": str(plan_path), "plan_id": approved_plan_id, "base_url": base_url, "prepared": prepared}
    return request, reservation, normalized, plan, Path(reservation_path).expanduser().resolve()


def execute_akeneo_products(request_path: str | Path, reservation_path: str | Path, client: AkeneoClient, *, audit_path: str | Path | None = None, state_path: str | Path | None = None) -> dict[str, Any]:
    _, reservation, approved, plan, reservation_file = _validated_inputs(request_path, reservation_path)
    if approved["base_url"] != client.base_url:
        raise ValueError("Approved Akeneo base_url does not match connector client")
    audit = Path(audit_path).expanduser().resolve() if audit_path else reservation_file.parent.parent / "execution_audit.jsonl"
    state_file = Path(state_path).expanduser().resolve() if state_path else reservation_file.parent.parent / "akeneo_execution_state.json"

    reservation["status"] = "consumed"
    reservation["consumed_at"] = _now()
    reservation["connector"] = "akeneo"
    reservation["external_action_performed"] = False
    _atomic_json(reservation_file, reservation)
    append_execution_audit(audit, {"event": "reservation_consumed", "request_id": reservation["request_id"], "action": ACTION, "idempotency_key": reservation["idempotency_key"], "status": "consumed", "external_action_performed": False, "payload": redact_secrets({"plan_id": approved["plan_id"], "base_url": approved["base_url"]})})

    state: dict[str, Any] = {
        "schema_version": 1,
        "mode": STATE_MODE,
        "created_at": _now(),
        "updated_at": _now(),
        "request_id": reservation["request_id"],
        "idempotency_key": reservation["idempotency_key"],
        "plan_id": approved["plan_id"],
        "profile_id": plan.get("profile_id"),
        "base_url": approved["base_url"],
        "status": "preflight",
        "records": [],
        "automatic_rollback_performed": False,
    }

    try:
        for prepared in approved["prepared"]:
            item = prepared["record"]
            identity = str(item["identity"])
            before = client.get_product(identity)
            state["records"].append({
                "identity": identity,
                "plan_fingerprint": item.get("fingerprint"),
                "request_payload_fingerprint": _fingerprint(prepared["payload"]),
                "before_exists": before is not None,
                "before": before,
                "before_fingerprint": _fingerprint(before) if before is not None else None,
                "write_status": "pending",
            })
        state["status"] = "ready_to_apply"
        state["updated_at"] = _now()
        _atomic_json(state_file, state)

        applied = 0
        for index, prepared in enumerate(approved["prepared"]):
            identity = str(prepared["record"]["identity"])
            client.patch_product(identity, prepared["payload"])
            applied += 1
            state["records"][index]["write_status"] = "applied"
            state["records"][index]["applied_at"] = _now()
            state["updated_at"] = _now()
            _atomic_json(state_file, state)

        state["status"] = "succeeded"
        state["completed_at"] = _now()
        state["updated_at"] = state["completed_at"]
        _atomic_json(state_file, state)
        result = record_execution_result(reservation_file, audit, status="succeeded", attempt=1, details={"connector": "akeneo", "operation": "apply_products", "plan_id": approved["plan_id"], "base_url": approved["base_url"], "records_applied": applied, "state_path": str(state_file), "automatic_rollback_performed": False}, external_action_performed=True)
        reservation.update({"status": "succeeded", "completed_at": _now(), "external_action_performed": True, "attempts": 1, "result_state_path": str(state_file)})
        _atomic_json(reservation_file, reservation)
        return result | {"state_path": str(state_file), "records_applied": applied, "automatic_rollback_performed": False}
    except Exception as exc:
        performed = any(item.get("write_status") == "applied" for item in state.get("records", []))
        state["status"] = "failed"
        state["completed_at"] = _now()
        state["updated_at"] = state["completed_at"]
        state["last_error"] = str(exc)
        state["reconciliation_required"] = performed
        _atomic_json(state_file, state)
        record_execution_result(reservation_file, audit, status="failed", attempt=1, details={"connector": "akeneo", "operation": "apply_products", "plan_id": approved["plan_id"], "base_url": approved["base_url"], "error": str(exc), "state_path": str(state_file), "reconciliation_required": performed, "automatic_rollback_performed": False}, external_action_performed=performed)
        reservation.update({"status": "failed", "completed_at": _now(), "external_action_performed": performed, "attempts": 1, "last_error": str(exc), "result_state_path": str(state_file)})
        _atomic_json(reservation_file, reservation)
        raise ValueError(f"Approved Akeneo product execution failed: {exc}") from exc


def reconcile_akeneo_execution(state_path: str | Path, client: AkeneoClient) -> dict[str, Any]:
    state = _read_json(state_path, STATE_MODE)
    if _normalize_base_url(str(state.get("base_url", ""))) != client.base_url:
        raise ValueError("Akeneo execution state belongs to a different base_url")
    results = []
    for item in state.get("records", []):
        identity = str(item.get("identity", ""))
        current = client.get_product(identity)
        results.append({
            "identity": identity,
            "write_status": item.get("write_status"),
            "before_exists": bool(item.get("before_exists")),
            "current_exists": current is not None,
            "before_fingerprint": item.get("before_fingerprint"),
            "current_fingerprint": _fingerprint(current) if current is not None else None,
            "changed_from_before": (_fingerprint(current) if current is not None else None) != item.get("before_fingerprint"),
        })
    return {"mode": "akeneo_execution_reconciliation", "state_path": str(Path(state_path).expanduser().resolve()), "base_url": client.base_url, "network_writes_performed": 0, "external_action_performed": False, "records": results}
