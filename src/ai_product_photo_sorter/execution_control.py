from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .approval_boundary import validate_grant

SCHEMA_VERSION = 1
DEFAULT_RETRY_POLICY = {"max_attempts": 3, "base_delay_seconds": 2.0, "max_delay_seconds": 30.0}
SENSITIVE_FRAGMENTS = (
    "authorization",
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(fragment in normalized for fragment in SENSITIVE_FRAGMENTS)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def idempotency_key(request_id: str, action: str, payload: dict[str, Any]) -> str:
    material = f"{request_id}\n{action}\n{_canonical(payload)}".encode("utf-8")
    return "idem_" + hashlib.sha256(material).hexdigest()[:24]


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
        temp.unlink(missing_ok=True)


def validate_retry_policy(value: dict[str, Any] | None) -> dict[str, Any]:
    policy = dict(DEFAULT_RETRY_POLICY if value is None else value)
    allowed = {"max_attempts", "base_delay_seconds", "max_delay_seconds"}
    unknown = set(policy) - allowed
    if unknown:
        raise ValueError("Unsupported retry policy field(s): " + ", ".join(sorted(unknown)))
    if isinstance(policy.get("max_attempts"), bool) or not isinstance(policy.get("max_attempts"), int):
        raise ValueError("retry_policy.max_attempts must be an integer")
    max_attempts = policy["max_attempts"]
    if max_attempts < 1 or max_attempts > 10:
        raise ValueError("retry_policy.max_attempts must be between 1 and 10")
    normalized: dict[str, Any] = {"max_attempts": max_attempts}
    for name in ("base_delay_seconds", "max_delay_seconds"):
        raw = policy.get(name)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"retry_policy.{name} must be a finite number")
        number = float(raw)
        if not math.isfinite(number) or number < 0 or number > 300:
            raise ValueError(f"retry_policy.{name} must be between 0 and 300 seconds")
        normalized[name] = number
    if normalized["max_delay_seconds"] < normalized["base_delay_seconds"]:
        raise ValueError("retry_policy.max_delay_seconds cannot be less than base_delay_seconds")
    return normalized


@contextmanager
def _audit_lock(path: Path, *, timeout_seconds: float = 5.0) -> Iterator[None]:
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError(f"Timed out waiting for execution audit lock: {lock}")
            time.sleep(0.01)
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode("ascii", errors="ignore"))
        os.fsync(fd)
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock.unlink(missing_ok=True)


def reserve_grant(
    request_path: str | Path,
    grant_path: str | Path,
    state_dir: str | Path,
    *,
    retry_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_grant(request_path, grant_path)
    request = _read_json(request_path, "approval_request")
    grant = _read_json(grant_path, "approval_grant")

    request_id = str(validation["request_id"])
    action = str(validation["action"])
    payload = dict(request.get("payload", {}))
    key = idempotency_key(request_id, action, payload)
    policy = validate_retry_policy(retry_policy)

    root = Path(state_dir).expanduser().resolve()
    reservations = root / "reservations"
    reservations.mkdir(parents=True, exist_ok=True)
    reservation_path = reservations / f"{request_id}.json"

    record = {
        "schema_version": SCHEMA_VERSION,
        "mode": "execution_reservation",
        "request_id": request_id,
        "action": action,
        "idempotency_key": key,
        "reserved_at": _now(),
        "grant_single_use": bool(grant.get("single_use", True)),
        "retry_policy": policy,
        "redacted_payload": redact_secrets(payload),
        "external_action_performed": False,
        "status": "reserved",
    }

    try:
        with reservation_path.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Approval grant has already been reserved: {request_id}") from exc

    append_execution_audit(root / "execution_audit.jsonl", {
        "event": "approval_reserved",
        "request_id": request_id,
        "action": action,
        "idempotency_key": key,
        "status": "reserved",
        "external_action_performed": False,
        "payload": redact_secrets(payload),
    })
    return record | {"reservation": str(reservation_path)}


def append_execution_audit(audit_path: str | Path, event: dict[str, Any]) -> Path:
    path = Path(audit_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": _now(),
        **redact_secrets(dict(event)),
    }
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with _audit_lock(path):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return path


def record_execution_result(
    reservation_path: str | Path,
    audit_path: str | Path,
    *,
    status: str,
    attempt: int,
    details: dict[str, Any] | None = None,
    external_action_performed: bool = False,
) -> dict[str, Any]:
    reservation = _read_json(reservation_path, "execution_reservation")
    normalized = status.strip().lower()
    if normalized not in {"succeeded", "failed", "cancelled"}:
        raise ValueError("status must be one of: succeeded, failed, cancelled")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("attempt must be an integer >= 1")
    policy = validate_retry_policy(reservation.get("retry_policy"))
    if attempt > policy["max_attempts"]:
        raise ValueError("attempt cannot exceed reservation retry_policy.max_attempts")

    result = {
        "event": "execution_result",
        "request_id": reservation.get("request_id"),
        "action": reservation.get("action"),
        "idempotency_key": reservation.get("idempotency_key"),
        "status": normalized,
        "attempt": attempt,
        "external_action_performed": bool(external_action_performed),
        "details": redact_secrets(details or {}),
    }
    append_execution_audit(audit_path, result)
    return result
