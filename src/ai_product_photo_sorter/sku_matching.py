"""Confidence-aware SKU/catalog candidate matching with mandatory human confirmation.

The matcher consumes only already-approved Review Center groups. Local OCR/barcode
artifacts can strengthen ranking, but even an exact barcode is a suggestion until
a human explicitly confirms it. Confirmation updates only this matcher manifest;
it never edits Review Center state, source photos, catalog files, or commerce data.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = "sku_match_manifest.json"
CANDIDATES_NAME = "sku_match_candidates.csv"
CONFIRMED_NAME = "confirmed_catalog_matches.csv"
AUDIT_NAME = "sku_match_audit.jsonl"

_IDENTIFIER_HEADERS = {
    "sku", "sku_id", "stock_code", "stockcode", "item", "item_code", "itemcode",
    "product_code", "productcode", "code", "model", "model_no", "model_number",
    "modelnumber", "mpn", "part", "part_no", "part_number", "partnumber",
}
_BARCODE_HEADERS = {
    "barcode", "bar_code", "ean", "ean13", "ean_13", "upc", "upca", "upc_a",
    "gtin", "gtin13", "gtin_13", "isbn",
}
_NAME_HEADERS = {
    "name", "product", "product_name", "productname", "description", "title",
    "brand", "category",
}
_HEADER_HINTS = _IDENTIFIER_HEADERS | _BARCODE_HEADERS | _NAME_HEADERS | {
    "price", "cost", "qty", "quantity", "stock",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).casefold()
    return "".join(char for char in text if char.isalnum())


def _header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).casefold().strip()
    text = re.sub(r"[^\w]+", "_", text, flags=re.UNICODE).strip("_")
    return text


def _tokens(value: Any) -> set[str]:
    text = unicodedata.normalize("NFKC", _text(value)).casefold()
    return {token for token in re.findall(r"[\w]+", text, flags=re.UNICODE) if len(token) >= 2}


def _unique_headers(values: list[Any]) -> list[str]:
    result: list[str] = []
    used: dict[str, int] = {}
    for index, value in enumerate(values, 1):
        base = _header(value) or f"column_{index}"
        used[base] = used.get(base, 0) + 1
        result.append(base if used[base] == 1 else f"{base}_{used[base]}")
    return result


def _looks_like_header(values: list[Any]) -> bool:
    normalized = {_header(value) for value in values if _text(value)}
    return bool(normalized & _HEADER_HINTS)


def _catalog_record(
    *,
    source_name: str,
    row_number: int,
    headers: list[str],
    values: list[Any],
) -> dict[str, Any] | None:
    rendered = [_text(value) for value in values]
    if not any(rendered):
        return None
    fields = {
        headers[index] if index < len(headers) else f"column_{index + 1}": value
        for index, value in enumerate(rendered)
        if value
    }
    row_id = f"{source_name}!R{row_number}"
    return {
        "row_id": row_id,
        "source": source_name,
        "row_number": row_number,
        "fields": fields,
        "search_text": " | ".join(rendered),
    }


def _read_xlsx(path: Path) -> list[dict[str, Any]]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    records: list[dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets:
            materialized: list[tuple[int, list[Any]]] = []
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                values = list(row)
                if any(_text(value) for value in values):
                    materialized.append((row_number, values))
            if not materialized:
                continue
            first_number, first_values = materialized[0]
            has_header = _looks_like_header(first_values)
            width = max(len(values) for _, values in materialized)
            headers = (
                _unique_headers(first_values + [""] * (width - len(first_values)))
                if has_header
                else [f"column_{index}" for index in range(1, width + 1)]
            )
            rows = materialized[1:] if has_header else materialized
            for row_number, values in rows:
                record = _catalog_record(
                    source_name=sheet.title,
                    row_number=row_number,
                    headers=headers,
                    values=values,
                )
                if record:
                    records.append(record)
    finally:
        workbook.close()
    return records


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [(index, row) for index, row in enumerate(csv.reader(handle), 1) if any(cell.strip() for cell in row)]
    if not rows:
        return []
    first_number, first_values = rows[0]
    has_header = _looks_like_header(first_values)
    width = max(len(values) for _, values in rows)
    headers = (
        _unique_headers(first_values + [""] * (width - len(first_values)))
        if has_header
        else [f"column_{index}" for index in range(1, width + 1)]
    )
    records: list[dict[str, Any]] = []
    for row_number, values in (rows[1:] if has_header else rows):
        record = _catalog_record(
            source_name=path.stem,
            row_number=row_number,
            headers=headers,
            values=values,
        )
        if record:
            records.append(record)
    return records


def load_catalog_rows(path: Path) -> list[dict[str, Any]]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Catalog file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        rows = _read_xlsx(path)
    elif suffix == ".csv":
        rows = _read_csv(path)
    else:
        raise ValueError("SKU matching currently supports .xlsx, .xlsm, or .csv catalogs")
    if not rows:
        raise ValueError("Catalog contains no non-empty product rows")
    return rows


def load_approved_groups(path: Path) -> list[dict[str, Any]]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Approved Review Center export does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError("Approved Review Center export contains no groups")
    required = {"group_id", "filenames"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(
            "Approved group export is missing required columns: " + ", ".join(sorted(missing))
        )
    groups: list[dict[str, Any]] = []
    for row in rows:
        group_id = str(row.get("group_id", "")).strip()
        if not group_id:
            raise ValueError("Approved group export contains an empty group_id")
        groups.append(
            {
                "group_id": group_id,
                "category": str(row.get("category", "")).strip(),
                "brand": str(row.get("brand", "")).strip(),
                "model": str(row.get("model", "")).strip(),
                "filenames": [
                    item.strip() for item in str(row.get("filenames", "")).split("|") if item.strip()
                ],
                "notes": str(row.get("notes", "")).strip(),
            }
        )
    return groups


def load_local_evidence(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Local evidence JSON does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read local evidence JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("photos"), list):
        raise ValueError("File is not a Product Sorter local evidence artifact")
    return {
        str(photo.get("filename", "")): photo
        for photo in payload["photos"]
        if isinstance(photo, dict) and str(photo.get("filename", "")).strip()
    }


def _group_evidence(group: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    barcodes: set[str] = set()
    labeled: set[str] = set()
    tokens: set[str] = set()
    source_photos = 0
    for filename in group.get("filenames", []):
        photo = evidence.get(filename)
        if not photo:
            continue
        source_photos += 1
        for row in photo.get("identifier_candidates", []):
            if not isinstance(row, dict):
                continue
            value = _text(row.get("value"))
            source = _text(row.get("source"))
            normalized = _norm(value)
            if not normalized:
                continue
            if source == "barcode":
                barcodes.add(normalized)
            elif source == "ocr_labeled":
                labeled.add(normalized)
            else:
                tokens.add(normalized)
        for row in photo.get("barcodes", []):
            if isinstance(row, dict) and _norm(row.get("text")):
                barcodes.add(_norm(row.get("text")))
    model = _norm(group.get("model"))
    if model:
        labeled.add(model)
    return {
        "barcodes": sorted(barcodes),
        "labeled_identifiers": sorted(labeled),
        "ocr_tokens": sorted(tokens),
        "evidence_photos": source_photos,
    }


def _row_indexes(row: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("fields", {})
    all_values = {_norm(value) for value in fields.values() if _norm(value)}
    barcode_values = {
        _norm(value)
        for key, value in fields.items()
        if _header(key) in _BARCODE_HEADERS and _norm(value)
    }
    identifier_values = {
        _norm(value)
        for key, value in fields.items()
        if _header(key) in (_IDENTIFIER_HEADERS | _BARCODE_HEADERS) and _norm(value)
    }
    if not barcode_values:
        barcode_values = {
            value for value in all_values if value.isdigit() and 8 <= len(value) <= 18
        }
    if not identifier_values:
        identifier_values = all_values
    return {
        "all_values": all_values,
        "barcode_values": barcode_values,
        "identifier_values": identifier_values,
        "search_tokens": _tokens(row.get("search_text", "")),
        "search_normalized": _norm(row.get("search_text", "")),
    }


def rank_catalog_rows(
    group: dict[str, Any],
    evidence: dict[str, Any],
    catalog_rows: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    group_brand = _norm(group.get("brand"))
    group_model = _norm(group.get("model"))
    group_category = _norm(group.get("category"))
    context_tokens = _tokens(
        " ".join(
            str(group.get(field, ""))
            for field in ("category", "brand", "model", "notes")
        )
    )
    barcodes = set(evidence.get("barcodes", []))
    labeled = set(evidence.get("labeled_identifiers", []))
    ocr_tokens = set(evidence.get("ocr_tokens", []))

    ranked: list[dict[str, Any]] = []
    for row in catalog_rows:
        index = _row_indexes(row)
        points = 0.0
        reasons: list[str] = []
        tier = "contextual"

        barcode_hits = sorted(barcodes & index["barcode_values"])
        if barcode_hits:
            points = max(points, 100.0)
            tier = "exact_barcode"
            reasons.append("exact barcode: " + ", ".join(barcode_hits[:3]))

        labeled_hits = sorted(labeled & index["identifier_values"])
        if labeled_hits:
            points = max(points, 92.0)
            if tier != "exact_barcode":
                tier = "exact_identifier"
            reasons.append("exact SKU/model identifier: " + ", ".join(labeled_hits[:3]))

        token_hits = sorted(ocr_tokens & index["identifier_values"])
        if token_hits:
            points = max(points, 70.0)
            if tier == "contextual":
                tier = "ocr_identifier"
            reasons.append("OCR identifier token: " + ", ".join(token_hits[:3]))

        row_normalized = index["search_normalized"]
        if group_model and group_model in index["identifier_values"]:
            points = max(points, 90.0)
            if tier == "contextual":
                tier = "exact_model"
            reasons.append("approved model exact match")
        elif group_model and group_model in row_normalized:
            points += 25.0
            reasons.append("approved model text overlap")

        if group_brand and group_brand in row_normalized:
            points += 12.0
            reasons.append("brand overlap")
        if group_category and group_category in row_normalized:
            points += 4.0
            reasons.append("category overlap")

        if context_tokens:
            overlap = context_tokens & index["search_tokens"]
            if overlap:
                ratio = len(overlap) / max(1, len(context_tokens))
                bonus = min(18.0, ratio * 18.0)
                points += bonus
                reasons.append("context tokens: " + ", ".join(sorted(overlap)[:5]))

        score = min(1.0, points / 100.0)
        if score <= 0.0:
            continue
        ranked.append(
            {
                "row_id": row["row_id"],
                "ranking_score": round(score, 6),
                "tier": tier,
                "reasons": reasons,
                "fields": row.get("fields", {}),
                "display": row.get("search_text", ""),
            }
        )

    ranked.sort(
        key=lambda item: (
            -float(item["ranking_score"]),
            str(item["row_id"]).casefold(),
        )
    )
    for index, candidate in enumerate(ranked[:top_k], 1):
        candidate["rank"] = index
    return ranked[:top_k]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _refresh(manifest: dict[str, Any]) -> dict[str, Any]:
    groups = manifest.get("groups", [])
    confirmed = sum(
        str(group.get("decision", {}).get("status", "pending")) == "confirmed"
        for group in groups
    )
    with_candidates = sum(bool(group.get("candidates")) for group in groups)
    exact_barcode = sum(
        bool(group.get("candidates")) and group["candidates"][0].get("tier") == "exact_barcode"
        for group in groups
    )
    manifest["summary"] = {
        "groups": len(groups),
        "groups_with_candidates": with_candidates,
        "groups_without_candidates": len(groups) - with_candidates,
        "confirmed_groups": confirmed,
        "pending_groups": len(groups) - confirmed,
        "top_exact_barcode_suggestions": exact_barcode,
        "catalog_ready_for_export": bool(groups) and confirmed == len(groups),
        "automatic_matching_enabled": False,
        "human_confirmation_required": True,
        "publishing_enabled": False,
    }
    manifest["updated_at"] = _now()
    return manifest["summary"]


def _write_candidates_csv(manifest: dict[str, Any], path: Path) -> None:
    fields = [
        "group_id", "rank", "row_id", "ranking_score", "tier", "reasons", "display",
        "decision_status",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for group in manifest.get("groups", []):
            decision = group.get("decision", {})
            for candidate in group.get("candidates", []):
                writer.writerow(
                    {
                        "group_id": group.get("group_id", ""),
                        "rank": candidate.get("rank", ""),
                        "row_id": candidate.get("row_id", ""),
                        "ranking_score": candidate.get("ranking_score", ""),
                        "tier": candidate.get("tier", ""),
                        "reasons": " | ".join(candidate.get("reasons", [])),
                        "display": candidate.get("display", ""),
                        "decision_status": decision.get("status", "pending"),
                    }
                )


def _write_confirmed_csv(manifest: dict[str, Any], path: Path) -> None:
    fields = [
        "group_id", "category", "brand", "model", "row_id", "ranking_score", "tier",
        "catalog_display", "confirmed_at",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for group in manifest.get("groups", []):
            decision = group.get("decision", {})
            if decision.get("status") != "confirmed":
                continue
            candidate = decision.get("candidate", {})
            writer.writerow(
                {
                    "group_id": group.get("group_id", ""),
                    "category": group.get("category", ""),
                    "brand": group.get("brand", ""),
                    "model": group.get("model", ""),
                    "row_id": candidate.get("row_id", ""),
                    "ranking_score": candidate.get("ranking_score", ""),
                    "tier": candidate.get("tier", ""),
                    "catalog_display": candidate.get("display", ""),
                    "confirmed_at": decision.get("confirmed_at", ""),
                }
            )


def _persist(manifest: dict[str, Any], manifest_path: Path) -> None:
    _refresh(manifest)
    _atomic_json(manifest_path, manifest)
    _write_candidates_csv(manifest, manifest_path.parent / CANDIDATES_NAME)
    _write_confirmed_csv(manifest, manifest_path.parent / CONFIRMED_NAME)


def generate_candidates(
    approved_groups: Path,
    catalog: Path,
    *,
    evidence_json: Path | None = None,
    output_dir: Path | None = None,
    top_k: int = 5,
) -> tuple[dict[str, Any], Path]:
    if top_k <= 0 or top_k > 50:
        raise ValueError("top_k must be between 1 and 50")
    groups = load_approved_groups(approved_groups)
    catalog_rows = load_catalog_rows(catalog)
    evidence = load_local_evidence(evidence_json)
    destination = (output_dir or approved_groups.expanduser().resolve().parent / "sku_matching").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    manifest_groups: list[dict[str, Any]] = []
    for group in groups:
        measured = _group_evidence(group, evidence)
        candidates = rank_catalog_rows(group, measured, catalog_rows, top_k=top_k)
        manifest_groups.append(
            {
                **group,
                "evidence": measured,
                "candidates": candidates,
                "decision": {"status": "pending", "row_id": "", "confirmed_at": ""},
            }
        )

    created = _now()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "mode": "sku_candidate_matching",
        "revision": 0,
        "created_at": created,
        "updated_at": created,
        "approved_groups_source": str(approved_groups.expanduser().resolve()),
        "catalog_source": str(catalog.expanduser().resolve()),
        "evidence_source": str(evidence_json.expanduser().resolve()) if evidence_json else "",
        "catalog_rows": len(catalog_rows),
        "top_k": top_k,
        "groups": manifest_groups,
    }
    path = destination / MANIFEST_NAME
    _persist(manifest, path)
    return manifest, path


def load_match_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"SKU match manifest does not exist: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read SKU match manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("mode") != "sku_candidate_matching":
        raise ValueError("File is not a Product Sorter SKU match manifest")
    _refresh(manifest)
    return manifest, path


def _match_group(manifest: dict[str, Any], group_id: str) -> dict[str, Any]:
    for group in manifest.get("groups", []):
        if str(group.get("group_id")) == group_id:
            return group
    raise ValueError(f"Unknown SKU match group: {group_id}")


def _append_audit(path: Path, event: dict[str, Any]) -> None:
    with (path.parent / AUDIT_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def confirm_candidate(manifest_path: Path, group_id: str, row_id: str) -> tuple[dict[str, Any], Path]:
    manifest, path = load_match_manifest(manifest_path)
    group = _match_group(manifest, group_id)
    candidate = next(
        (item for item in group.get("candidates", []) if str(item.get("row_id")) == row_id),
        None,
    )
    if candidate is None:
        raise ValueError(f"Catalog row {row_id!r} is not a current candidate for {group_id}")
    confirmed_at = _now()
    group["decision"] = {
        "status": "confirmed",
        "row_id": row_id,
        "confirmed_at": confirmed_at,
        "candidate": candidate,
    }
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    _persist(manifest, path)
    _append_audit(
        path,
        {
            "revision": manifest["revision"],
            "timestamp": confirmed_at,
            "action": "confirm",
            "group_id": group_id,
            "row_id": row_id,
            "automatic": False,
        },
    )
    return manifest, path


def clear_confirmation(manifest_path: Path, group_id: str) -> tuple[dict[str, Any], Path]:
    manifest, path = load_match_manifest(manifest_path)
    group = _match_group(manifest, group_id)
    previous = str(group.get("decision", {}).get("row_id", ""))
    group["decision"] = {"status": "pending", "row_id": "", "confirmed_at": ""}
    timestamp = _now()
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    _persist(manifest, path)
    _append_audit(
        path,
        {
            "revision": manifest["revision"],
            "timestamp": timestamp,
            "action": "clear_confirmation",
            "group_id": group_id,
            "previous_row_id": previous,
            "automatic": False,
        },
    )
    return manifest, path


def _print_help() -> None:
    print(
        "\nHuman-confirmed SKU/catalog matching:\n"
        "  --sku-match APPROVED.csv         Generate ranked candidates from approved Review Center groups\n"
        "  --sku-catalog FILE               Catalog .xlsx/.xlsm/.csv used for candidate ranking\n"
        "  --sku-evidence JSON              Optional local_catalog_evidence.json\n"
        "  --sku-output DIR                 Candidate manifest/output directory\n"
        "  --sku-top-k N                    Candidate rows retained per group (default 5)\n"
        "  --sku-confirm MANIFEST           Confirm one candidate (requires --sku-group and --sku-row)\n"
        "  --sku-clear MANIFEST             Clear one confirmation (requires --sku-group)\n"
        "  --sku-group ID                   Review group id for confirm/clear\n"
        "  --sku-row ROW_ID                 Catalog row id to confirm"
    )


def apply_sku_matching(module: Any) -> None:
    """Add standalone SKU candidate/confirmation actions without changing normal runs."""

    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--sku-match", type=Path)
        parser.add_argument("--sku-catalog", type=Path)
        parser.add_argument("--sku-evidence", type=Path)
        parser.add_argument("--sku-output", type=Path)
        parser.add_argument("--sku-top-k", type=int, default=5)
        parser.add_argument("--sku-confirm", type=Path)
        parser.add_argument("--sku-clear", type=Path)
        parser.add_argument("--sku-group")
        parser.add_argument("--sku-row")
        known, remaining = parser.parse_known_args(original[1:])

        try:
            if known.sku_match is not None:
                if known.sku_catalog is None:
                    raise SystemExit("--sku-match requires --sku-catalog")
                manifest, path = generate_candidates(
                    known.sku_match,
                    known.sku_catalog,
                    evidence_json=known.sku_evidence,
                    output_dir=known.sku_output,
                    top_k=known.sku_top_k,
                )
                summary = manifest["summary"]
                print(f"SKU match manifest: {path}")
                print(f"Candidate CSV: {path.parent / CANDIDATES_NAME}")
                print(
                    f"Groups: {summary['groups']} · candidates: {summary['groups_with_candidates']} · "
                    f"confirmed: {summary['confirmed_groups']}"
                )
                print("Suggestions only: every catalog match requires explicit human confirmation.")
                raise SystemExit(0)

            if known.sku_confirm is not None:
                if not known.sku_group or not known.sku_row:
                    raise SystemExit("--sku-confirm requires --sku-group and --sku-row")
                manifest, path = confirm_candidate(known.sku_confirm, known.sku_group, known.sku_row)
                print(f"Confirmed catalog candidate: {known.sku_group} -> {known.sku_row}")
                print(json.dumps(manifest["summary"], ensure_ascii=False, sort_keys=True))
                print(f"Confirmed matches: {path.parent / CONFIRMED_NAME}")
                raise SystemExit(0)

            if known.sku_clear is not None:
                if not known.sku_group:
                    raise SystemExit("--sku-clear requires --sku-group")
                manifest, path = clear_confirmation(known.sku_clear, known.sku_group)
                print(f"Cleared catalog confirmation: {known.sku_group}")
                print(json.dumps(manifest["summary"], ensure_ascii=False, sort_keys=True))
                print(f"Confirmed matches: {path.parent / CONFIRMED_NAME}")
                raise SystemExit(0)

            sku_flags = {
                "--sku-catalog", "--sku-evidence", "--sku-output", "--sku-top-k",
                "--sku-group", "--sku-row",
            }
            if any(flag in original for flag in sku_flags):
                raise SystemExit("SKU matching options require --sku-match, --sku-confirm, or --sku-clear")

            sys.argv = [original[0], *remaining]
            return base_parse_args(env_file)
        except (ValueError, OSError) as exc:
            raise SystemExit(str(exc)) from exc
        except SystemExit as exc:
            if exc.code == 0 and any(flag in original for flag in ("-h", "--help")):
                _print_help()
            raise
        finally:
            sys.argv = original

    module.parse_args = parse_args
