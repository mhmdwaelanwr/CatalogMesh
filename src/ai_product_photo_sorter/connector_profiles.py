from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PROFILE_MODE = "catalog_connector_profile"
PLAN_MODE = "catalog_connector_write_plan"
DEFAULT_PLAN_NAME = "connector_write_plan.json"
ALLOWED_KINDS = {"pim", "erp"}
SENSITIVE_FRAGMENTS = ("token", "secret", "password", "credential", "authorization", "api_key", "apikey", "access_key", "private_key")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"File does not exist: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON file {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {source}")
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


def _reject_embedded_secrets(value: Any, path: str = "profile") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if any(fragment in normalized for fragment in SENSITIVE_FRAGMENTS):
                raise ValueError(f"Connector profiles must not embed credential fields: {path}.{key}")
            _reject_embedded_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_embedded_secrets(item, f"{path}[{index}]")


def load_connector_profile(path: str | Path) -> dict[str, Any]:
    profile = _read_json(path)
    if profile.get("mode") != PROFILE_MODE:
        raise ValueError("File is not a Product Sorter catalog connector profile")
    if int(profile.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported connector profile schema_version: {profile.get('schema_version')}")
    _reject_embedded_secrets(profile)
    profile_id = str(profile.get("profile_id", "")).strip()
    kind = str(profile.get("connector_kind", "")).strip().lower()
    entity = str(profile.get("entity", "")).strip()
    identity_source = str(profile.get("identity_source", "")).strip()
    field_map = profile.get("field_map")
    if not profile_id or not entity or not identity_source:
        raise ValueError("Connector profile requires profile_id, entity, and identity_source")
    if kind not in ALLOWED_KINDS:
        raise ValueError("connector_kind must be one of: pim, erp")
    if not isinstance(field_map, dict) or not field_map:
        raise ValueError("Connector profile field_map must be a non-empty object")
    normalized_map: dict[str, str] = {}
    target_fields: set[str] = set()
    for source, target in field_map.items():
        source_name = str(source).strip()
        target_name = str(target).strip()
        if not source_name or not target_name:
            raise ValueError("Connector profile field_map names cannot be blank")
        if target_name in target_fields:
            raise ValueError(f"Connector profile maps multiple source fields to target field: {target_name}")
        normalized_map[source_name] = target_name
        target_fields.add(target_name)
    if identity_source not in normalized_map:
        raise ValueError("identity_source must be included in field_map")
    required = profile.get("required_source_fields", [identity_source])
    if not isinstance(required, list) or any(not str(item).strip() for item in required):
        raise ValueError("required_source_fields must be a list of non-empty field names")
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": PROFILE_MODE,
        "profile_id": profile_id,
        "connector_kind": kind,
        "entity": entity,
        "identity_source": identity_source,
        "field_map": normalized_map,
        "required_source_fields": [str(item).strip() for item in required],
    }


def _load_neutral_export(export_manifest: str | Path) -> tuple[dict[str, Any], Path, list[dict[str, str]]]:
    source = Path(export_manifest).expanduser().resolve()
    manifest = _read_json(source)
    if manifest.get("mode") != "catalog_export_profiles":
        raise ValueError("File is not a Product Sorter catalog export manifest")
    if bool(manifest.get("publishing_enabled")) or int(manifest.get("network_calls_performed", 0)) != 0:
        raise ValueError("Connector planning accepts only offline, non-publishing catalog exports")
    output = str(manifest.get("outputs", {}).get("neutral_pim_csv", "")).strip()
    if not output:
        raise ValueError("Catalog export manifest does not contain neutral_pim_csv")
    csv_path = Path(output)
    if not csv_path.is_absolute():
        csv_path = source.parent / csv_path
    csv_path = csv_path.expanduser().resolve()
    if not csv_path.is_file():
        raise ValueError(f"Neutral PIM CSV does not exist: {csv_path}")
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise ValueError(f"Could not read neutral PIM CSV: {exc}") from exc
    if not rows:
        raise ValueError("Neutral PIM CSV contains no products")
    return manifest, csv_path, rows


def build_connector_plan(export_manifest: str | Path, profile_path: str | Path, *, output: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    profile = load_connector_profile(profile_path)
    manifest, csv_path, rows = _load_neutral_export(export_manifest)
    records: list[dict[str, Any]] = []
    required = profile["required_source_fields"]
    field_map = profile["field_map"]
    for row_number, row in enumerate(rows, start=2):
        missing = [name for name in required if not str(row.get(name, "")).strip()]
        if missing:
            raise ValueError(f"Connector plan row {row_number} is missing required source field(s): {', '.join(missing)}")
        identity = str(row.get(profile["identity_source"], "")).strip()
        mapped = {target: str(row.get(source, "")).strip() for source, target in field_map.items()}
        fingerprint = hashlib.sha256(_canonical({"identity": identity, "fields": mapped}).encode("utf-8")).hexdigest()
        records.append({"row_number": row_number, "identity": identity, "fields": mapped, "fingerprint": fingerprint})
    plan_core = {
        "profile_id": profile["profile_id"],
        "connector_kind": profile["connector_kind"],
        "entity": profile["entity"],
        "identity_source": profile["identity_source"],
        "records": records,
    }
    plan_id = "cplan_" + hashlib.sha256(_canonical(plan_core).encode("utf-8")).hexdigest()[:20]
    plan = {
        "schema_version": SCHEMA_VERSION,
        "mode": PLAN_MODE,
        "plan_id": plan_id,
        "created_at": _now(),
        "action": f"{profile['connector_kind']}.apply_profile",
        "profile": profile,
        "source_export_manifest": str(Path(export_manifest).expanduser().resolve()),
        "source_neutral_pim_csv": str(csv_path),
        "source_products": int(manifest.get("products", len(records))),
        "records": records,
        "network_calls_performed": 0,
        "external_action_performed": False,
        "human_approval_required": True,
        "credentials_embedded": False,
    }
    destination = Path(output).expanduser().resolve() if output else Path(export_manifest).expanduser().resolve().parent / DEFAULT_PLAN_NAME
    _atomic_json(destination, plan)
    return plan, destination
