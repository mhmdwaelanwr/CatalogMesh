"""Non-destructive product-group review workflow.

Review Center converts ``classification_report.csv`` into a versioned review
manifest. Human corrections mutate only that manifest plus an append-only audit
log; Product Sorter's materialized photo outputs and source originals remain
untouched. Later SKU/export stages can therefore consume only explicitly
approved groups.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = "product_review_manifest.json"
AUDIT_NAME = "product_review_audit.jsonl"
SUMMARY_NAME = "product_review_summary.csv"
APPROVED_NAME = "approved_product_groups.csv"
REPORT_NAME = "classification_report.csv"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_report(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"Classification report does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except csv.Error as exc:
        raise ValueError(f"Could not read classification report {path}: {exc}") from exc
    if not rows:
        raise ValueError("Classification report contains no product photos")
    required = {"filename", "product_group", "category", "view", "status"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(
            "Classification report is missing required columns: "
            + ", ".join(sorted(missing))
        )
    return rows


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _common(values: list[str], default: str = "") -> str:
    filtered = [value.strip() for value in values if value and value.strip()]
    if not filtered:
        return default
    return Counter(filtered).most_common(1)[0][0]


def _relative_output_path(row: dict[str, str]) -> str:
    group = str(row.get("product_group", "")).strip()
    category = str(row.get("category", "other")).strip() or "other"
    status = str(row.get("status", "")).strip().lower()
    filename = str(row.get("output_filename") or row.get("filename") or "").strip()
    parent = "Needs_Review" if status == "needs_review" else category
    return Path(parent, group, filename).as_posix()


def build_manifest(output_root: Path) -> dict[str, Any]:
    output_root = output_root.expanduser().resolve()
    rows = _read_report(output_root / REPORT_NAME)
    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    fallback_index = 0
    for row in rows:
        group_id = str(row.get("product_group", "")).strip()
        if not group_id:
            fallback_index += 1
            group_id = f"Unassigned_{fallback_index:04d}"
        if group_id not in grouped:
            grouped[group_id] = []
            order.append(group_id)
        grouped[group_id].append(row)

    groups: list[dict[str, Any]] = []
    for group_id in order:
        group_rows = grouped[group_id]
        photos: list[dict[str, Any]] = []
        for row in group_rows:
            photos.append(
                {
                    "filename": str(row.get("filename", "")).strip(),
                    "output_filename": str(
                        row.get("output_filename") or row.get("filename") or ""
                    ).strip(),
                    "view": str(row.get("view", "unknown")).strip() or "unknown",
                    "confidence": _float(row.get("confidence")),
                    "original_status": str(row.get("status", "")).strip(),
                    "reason": str(row.get("reason", "")).strip(),
                    "relative_path": _relative_output_path(row),
                }
            )
        groups.append(
            {
                "group_id": group_id,
                "original_group_id": group_id,
                "category": _common(
                    [str(row.get("category", "")) for row in group_rows], "other"
                ),
                "brand": _common([str(row.get("brand", "")) for row in group_rows]),
                "model": _common([str(row.get("model", "")) for row in group_rows]),
                "catalog_match_original": _common(
                    [str(row.get("catalog_match", "")) for row in group_rows]
                ),
                "approved": False,
                "notes": "",
                "photos": photos,
            }
        )

    created = _now()
    manifest = {
        "schema_version": 1,
        "mode": "review_manifest",
        "output_root": str(output_root),
        "source_report": str(output_root / REPORT_NAME),
        "revision": 0,
        "audit_events": 0,
        "created_at": created,
        "updated_at": created,
        "groups": groups,
    }
    _refresh_manifest(manifest)
    return manifest


def _refresh_manifest(manifest: dict[str, Any]) -> None:
    groups = manifest.get("groups")
    if not isinstance(groups, list):
        raise ValueError("Review manifest groups must be a list")
    photo_count = sum(len(group.get("photos", [])) for group in groups)
    approved = sum(bool(group.get("approved")) for group in groups)
    manifest["group_count"] = len(groups)
    manifest["photo_count"] = photo_count
    manifest["approved_groups"] = approved
    manifest["pending_groups"] = len(groups) - approved
    manifest["catalog_ready"] = bool(groups) and approved == len(groups)
    manifest["updated_at"] = _now()


def _manifest_path(path_or_dir: Path) -> Path:
    path_or_dir = path_or_dir.expanduser().resolve()
    if path_or_dir.is_dir():
        return path_or_dir / MANIFEST_NAME
    return path_or_dir


def load_manifest(path_or_dir: Path) -> tuple[dict[str, Any], Path]:
    path = _manifest_path(path_or_dir)
    if not path.is_file():
        raise ValueError(f"Review manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read review manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != "review_manifest":
        raise ValueError("File is not a Product Sorter review manifest")
    _refresh_manifest(payload)
    return payload, path


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _summary_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in manifest.get("groups", []):
        photos = group.get("photos", [])
        rows.append(
            {
                "group_id": group.get("group_id", ""),
                "category": group.get("category", ""),
                "brand": group.get("brand", ""),
                "model": group.get("model", ""),
                "photo_count": len(photos),
                "approved": "true" if group.get("approved") else "false",
                "needs_review_photos": sum(
                    str(photo.get("original_status", "")).lower() == "needs_review"
                    for photo in photos
                ),
                "notes": group.get("notes", ""),
            }
        )
    return rows


def write_manifest(manifest: dict[str, Any], path_or_dir: Path) -> Path:
    path = _manifest_path(path_or_dir)
    _refresh_manifest(manifest)
    _atomic_json(path, manifest)
    rows = _summary_rows(manifest)
    summary = path.parent / SUMMARY_NAME
    with summary.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = [
            "group_id",
            "category",
            "brand",
            "model",
            "photo_count",
            "approved",
            "needs_review_photos",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def initialize_review(output_root: Path) -> tuple[dict[str, Any], Path]:
    manifest = build_manifest(output_root)
    path = write_manifest(manifest, output_root)
    return manifest, path


def review_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    _refresh_manifest(manifest)
    groups = manifest["groups"]
    needs_review_photos = sum(
        str(photo.get("original_status", "")).lower() == "needs_review"
        for group in groups
        for photo in group.get("photos", [])
    )
    return {
        "groups": manifest["group_count"],
        "photos": manifest["photo_count"],
        "approved_groups": manifest["approved_groups"],
        "pending_groups": manifest["pending_groups"],
        "needs_review_photos": needs_review_photos,
        "catalog_ready": manifest["catalog_ready"],
        "revision": int(manifest.get("revision", 0)),
        "audit_events": int(manifest.get("audit_events", 0)),
    }


def _group(manifest: dict[str, Any], group_id: str) -> dict[str, Any]:
    for group in manifest.get("groups", []):
        if str(group.get("group_id")) == group_id:
            return group
    raise ValueError(f"Unknown review group: {group_id}")


def _unique_group_id(manifest: dict[str, Any], preferred: str) -> str:
    preferred = preferred.strip()
    if not preferred:
        raise ValueError("New group id cannot be empty")
    existing = {str(group.get("group_id")) for group in manifest.get("groups", [])}
    if preferred not in existing:
        return preferred
    for index in range(2, 10_000):
        candidate = f"{preferred}_{index}"
        if candidate not in existing:
            return candidate
    raise ValueError(f"Could not create a unique group id from {preferred!r}")


def _photo_location(manifest: dict[str, Any], filename: str) -> tuple[dict[str, Any], dict[str, Any]]:
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for group in manifest.get("groups", []):
        for photo in group.get("photos", []):
            if str(photo.get("filename")) == filename:
                matches.append((group, photo))
    if not matches:
        raise ValueError(f"Unknown photo in review manifest: {filename}")
    if len(matches) > 1:
        raise ValueError(f"Photo filename is not unique in review manifest: {filename}")
    return matches[0]


def _apply_operation(manifest: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    action = str(operation.get("action", "")).strip().lower()
    if action in {"approve", "unapprove"}:
        group = _group(manifest, str(operation.get("group", "")))
        group["approved"] = action == "approve"
        return {"group": group["group_id"], "approved": group["approved"]}

    if action == "set_group":
        group = _group(manifest, str(operation.get("group", "")))
        changed: dict[str, Any] = {"group": group["group_id"]}
        for field in ("category", "brand", "model", "notes"):
            if field in operation:
                value = str(operation.get(field, "")).strip()
                group[field] = value
                changed[field] = value
        group["approved"] = False
        changed["approved"] = False
        return changed

    if action == "set_view":
        filename = str(operation.get("filename", "")).strip()
        view = str(operation.get("view", "")).strip()
        if not view:
            raise ValueError("set_view requires a non-empty view")
        group, photo = _photo_location(manifest, filename)
        photo["view"] = view
        group["approved"] = False
        return {"filename": filename, "view": view, "group": group["group_id"]}

    if action == "move_photo":
        filename = str(operation.get("filename", "")).strip()
        destination = _group(manifest, str(operation.get("to_group", "")))
        source, photo = _photo_location(manifest, filename)
        if source is destination:
            return {"filename": filename, "from": source["group_id"], "to": destination["group_id"]}
        source["photos"].remove(photo)
        destination["photos"].append(photo)
        source["approved"] = False
        destination["approved"] = False
        if not source["photos"]:
            manifest["groups"].remove(source)
        return {"filename": filename, "from": source["group_id"], "to": destination["group_id"]}

    if action == "split":
        source = _group(manifest, str(operation.get("group", "")))
        filenames = [str(value).strip() for value in operation.get("filenames", []) if str(value).strip()]
        if not filenames:
            raise ValueError("split requires at least one filename")
        selected = [photo for photo in source.get("photos", []) if photo.get("filename") in filenames]
        if len(selected) != len(set(filenames)):
            raise ValueError("split contains photos that are not all present in the source group")
        if len(selected) >= len(source.get("photos", [])):
            raise ValueError("split must leave at least one photo in the source group")
        new_id = _unique_group_id(
            manifest,
            str(operation.get("new_group") or f"{source['group_id']}_split"),
        )
        for photo in selected:
            source["photos"].remove(photo)
        new_group = {
            "group_id": new_id,
            "original_group_id": source.get("original_group_id", source["group_id"]),
            "category": str(operation.get("category", source.get("category", "other"))),
            "brand": str(operation.get("brand", source.get("brand", ""))),
            "model": str(operation.get("model", source.get("model", ""))),
            "catalog_match_original": "",
            "approved": False,
            "notes": str(operation.get("notes", "")),
            "photos": selected,
        }
        source["approved"] = False
        index = manifest["groups"].index(source)
        manifest["groups"].insert(index + 1, new_group)
        return {"group": source["group_id"], "new_group": new_id, "photos": filenames}

    if action == "merge":
        group_ids = [str(value).strip() for value in operation.get("groups", []) if str(value).strip()]
        if len(set(group_ids)) < 2:
            raise ValueError("merge requires at least two different groups")
        target_id = str(operation.get("target") or group_ids[0]).strip()
        if target_id not in group_ids:
            raise ValueError("merge target must be included in groups")
        target = _group(manifest, target_id)
        sources = [_group(manifest, group_id) for group_id in group_ids if group_id != target_id]
        for source in sources:
            target["photos"].extend(source.get("photos", []))
            manifest["groups"].remove(source)
        target["approved"] = False
        return {"target": target_id, "merged": [group["group_id"] for group in sources]}

    raise ValueError(f"Unsupported review action: {action or '<empty>'}")


def _append_audit(path: Path, events: list[dict[str, Any]]) -> None:
    audit_path = path.parent / AUDIT_NAME
    with audit_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def apply_review_plan(manifest_path: Path, plan_path: Path) -> tuple[dict[str, Any], Path]:
    manifest, resolved = load_manifest(manifest_path)
    plan_path = plan_path.expanduser().resolve()
    if not plan_path.is_file():
        raise ValueError(f"Review plan does not exist: {plan_path}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read review plan {plan_path}: {exc}") from exc
    operations = plan.get("operations") if isinstance(plan, dict) else None
    if not isinstance(operations, list) or not operations:
        raise ValueError("Review plan must contain a non-empty operations list")

    events: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("Every review plan operation must be an object")
        details = _apply_operation(manifest, operation)
        manifest["revision"] = int(manifest.get("revision", 0)) + 1
        event = {
            "revision": manifest["revision"],
            "at": _now(),
            "action": str(operation.get("action", "")).strip().lower(),
            "details": details,
        }
        events.append(event)
    manifest["audit_events"] = int(manifest.get("audit_events", 0)) + len(events)
    write_manifest(manifest, resolved)
    _append_audit(resolved, events)
    return manifest, resolved


def export_approved(manifest_path: Path, output: Path | None = None) -> tuple[dict[str, Any], Path]:
    manifest, resolved = load_manifest(manifest_path)
    destination = (output or resolved.parent / APPROVED_NAME).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for group in manifest.get("groups", []):
        if not group.get("approved"):
            continue
        filenames = [str(photo.get("filename", "")) for photo in group.get("photos", [])]
        views = [str(photo.get("view", "")) for photo in group.get("photos", [])]
        rows.append(
            {
                "group_id": group.get("group_id", ""),
                "category": group.get("category", ""),
                "brand": group.get("brand", ""),
                "model": group.get("model", ""),
                "photo_count": len(filenames),
                "filenames": " | ".join(filenames),
                "views": " | ".join(views),
                "notes": group.get("notes", ""),
            }
        )
    fields = ["group_id", "category", "brand", "model", "photo_count", "filenames", "views", "notes"]
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "approved_groups": len(rows),
        "pending_groups": int(manifest.get("pending_groups", 0)),
        "catalog_ready": bool(manifest.get("catalog_ready")),
        "path": str(destination),
    }
    return summary, destination


def _print_help() -> None:
    print(
        "\nReview Center (non-destructive):\n"
        "  --review-init OUTPUT_DIR            Build product_review_manifest.json from classification_report.csv\n"
        "  --review-summary MANIFEST           Print current approval/review summary and exit\n"
        "  --review-apply MANIFEST             Apply operations from --review-plan JSON and exit\n"
        "  --review-plan FILE                  JSON operation plan for --review-apply\n"
        "  --review-export-approved MANIFEST   Export approved product groups to CSV and exit\n"
        "  --review-approved-out FILE          Optional approved-groups CSV destination"
    )


def apply_review_center(module: Any) -> None:
    """Add standalone review CLI actions without changing normal sorter runs."""
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--review-init", type=Path)
        parser.add_argument("--review-summary", type=Path)
        parser.add_argument("--review-apply", type=Path)
        parser.add_argument("--review-plan", type=Path)
        parser.add_argument("--review-export-approved", type=Path)
        parser.add_argument("--review-approved-out", type=Path)
        known, remaining = parser.parse_known_args(original[1:])
        actions = [
            known.review_init is not None,
            known.review_summary is not None,
            known.review_apply is not None,
            known.review_export_approved is not None,
        ]
        if sum(actions) > 1:
            raise SystemExit("Choose only one Review Center standalone action")
        try:
            if known.review_init is not None:
                manifest, path = initialize_review(known.review_init)
                summary = review_summary(manifest)
                print(f"Review manifest: {path}")
                print(
                    f"Groups: {summary['groups']} · photos: {summary['photos']} · "
                    f"pending: {summary['pending_groups']}"
                )
                raise SystemExit(0)
            if known.review_summary is not None:
                manifest, path = load_manifest(known.review_summary)
                summary = review_summary(manifest)
                print(f"Review manifest: {path}")
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                raise SystemExit(0)
            if known.review_apply is not None:
                if known.review_plan is None:
                    raise SystemExit("--review-apply requires --review-plan")
                manifest, path = apply_review_plan(known.review_apply, known.review_plan)
                summary = review_summary(manifest)
                print(f"Review manifest updated: {path}")
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                raise SystemExit(0)
            if known.review_export_approved is not None:
                summary, path = export_approved(
                    known.review_export_approved,
                    output=known.review_approved_out,
                )
                print(f"Approved groups: {path}")
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                raise SystemExit(0)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        review_flags = {"--review-plan", "--review-approved-out"}
        if any(flag in original for flag in review_flags):
            raise SystemExit("Review Center option requires its matching standalone action")
        try:
            sys.argv = [original[0], *remaining]
            return base_parse_args(env_file)
        except SystemExit as exc:
            if exc.code == 0 and any(flag in original for flag in ("-h", "--help")):
                _print_help()
            raise
        finally:
            sys.argv = original

    module.parse_args = parse_args
