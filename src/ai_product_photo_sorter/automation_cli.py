from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .approval_boundary import approve_request, create_approval_request, validate_grant
from .catalog_exports import generate_exports
from .execution_control import record_execution_result, reserve_grant
from .ingestion import scan_image_folder
from .missing_assets import find_missing_assets, find_missing_local_images
from .review_automation import open_review_queue
from .shopify_execution import execute_shopify_stage
from .shopify_publishing import API_VERSION, ShopifyClient
from .sku_matching import generate_candidates, load_catalog_rows
from .watch_daemon import main as watch_main


def _catalog_fields(path: Path) -> list[dict[str, Any]]:
    return [dict(row.get("fields", {})) for row in load_catalog_rows(path)]


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Approval payload must be a JSON object")
    return payload


def _shopify_client_from_env(store_domain: str | None = None, api_version: str | None = None) -> ShopifyClient:
    domain = (store_domain or os.getenv("SHOPIFY_STORE_DOMAIN", "")).strip()
    token = os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
    if not domain:
        raise ValueError("SHOPIFY_STORE_DOMAIN is required for approved Shopify execution")
    if not token:
        raise ValueError("SHOPIFY_ADMIN_ACCESS_TOKEN is required for approved Shopify execution")
    return ShopifyClient(domain, token, api_version=api_version or os.getenv("SHOPIFY_API_VERSION", API_VERSION))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="product-sorter-automation", description="Safe local catalog-image automation commands for Product Sorter")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a product-shoot folder without modifying it")
    scan.add_argument("root", type=Path)
    scan.add_argument("--no-recursive", action="store_true")

    missing = sub.add_parser("missing-assets", help="Show catalog SKUs with no image reference")
    missing.add_argument("catalog", type=Path)
    missing.add_argument("--sku-column", default="sku")
    missing.add_argument("--asset-column", action="append", dest="asset_columns")

    missing_local = sub.add_parser("missing-local", help="Show catalog SKUs without an exact same-stem local image candidate")
    missing_local.add_argument("catalog", type=Path)
    missing_local.add_argument("shoot", type=Path)
    missing_local.add_argument("--sku-column", default="sku")

    propose = sub.add_parser("propose-matches", help="Generate ranked SKU candidates from already-approved product groups")
    propose.add_argument("approved_groups", type=Path)
    propose.add_argument("catalog", type=Path)
    propose.add_argument("--evidence", type=Path)
    propose.add_argument("--output", type=Path)
    propose.add_argument("--top-k", type=int, default=5)

    review = sub.add_parser("open-review-queue", help="Read pending Review Center groups without mutating review state")
    review.add_argument("review_manifest", type=Path)
    review.add_argument("--limit", type=int, default=50)

    draft = sub.add_parser("prepare-shopify-draft", help="Prepare an offline Shopify draft from fully human-confirmed SKU matches")
    draft.add_argument("match_manifest", type=Path)
    draft.add_argument("--output", type=Path)

    request = sub.add_parser("request-external-action", help="Create a local approval request for a future external action; performs no external write")
    request.add_argument("action")
    request.add_argument("payload_json", type=Path)
    request.add_argument("output", type=Path)

    approve = sub.add_parser("approve-external-action", help="Human-only CLI approval for a local action request")
    approve.add_argument("request", type=Path)
    approve.add_argument("grant", type=Path)
    approve.add_argument("--confirm", required=True)

    validate = sub.add_parser("validate-approval", help="Validate that a local approval grant matches its request")
    validate.add_argument("request", type=Path)
    validate.add_argument("grant", type=Path)

    reserve = sub.add_parser("reserve-approved-action", help="Consume a grant into a single-use local execution reservation; performs no external write")
    reserve.add_argument("request", type=Path)
    reserve.add_argument("grant", type=Path)
    reserve.add_argument("state_dir", type=Path)

    result = sub.add_parser("record-execution-result", help="Append a redacted local connector-result audit event")
    result.add_argument("reservation", type=Path)
    result.add_argument("audit", type=Path)
    result.add_argument("--status", required=True, choices=["succeeded", "failed", "cancelled"])
    result.add_argument("--attempt", type=int, required=True)
    result.add_argument("--details", type=Path)
    result.add_argument("--external-action-performed", action="store_true")

    shopify_stage = sub.add_parser("execute-shopify-stage", help="Consume one approved reservation to stage Shopify products as unpublished DRAFT only")
    shopify_stage.add_argument("request", type=Path)
    shopify_stage.add_argument("reservation", type=Path)
    shopify_stage.add_argument("--audit", type=Path)
    shopify_stage.add_argument("--store")
    shopify_stage.add_argument("--api-version")

    watch = sub.add_parser("watch", help="Run the persistent watched-folder daemon")
    watch.add_argument("root", type=Path)
    watch.add_argument("--state", type=Path, default=Path(".product-sorter-watch.json"))
    watch.add_argument("--interval", type=float, default=5.0)
    watch.add_argument("--no-recursive", action="store_true")
    watch.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            _emit([item.to_dict() for item in scan_image_folder(args.root, recursive=not args.no_recursive)])
            return 0
        if args.command == "missing-assets":
            kwargs: dict[str, Any] = {"sku_column": args.sku_column}
            if args.asset_columns:
                kwargs["asset_columns"] = tuple(args.asset_columns)
            _emit([item.to_dict() for item in find_missing_assets(_catalog_fields(args.catalog), **kwargs)])
            return 0
        if args.command == "missing-local":
            images = scan_image_folder(args.shoot)
            _emit([item.to_dict() for item in find_missing_local_images(_catalog_fields(args.catalog), [asset.path for asset in images], sku_column=args.sku_column)])
            return 0
        if args.command == "propose-matches":
            manifest, path = generate_candidates(args.approved_groups, args.catalog, evidence_json=args.evidence, output_dir=args.output, top_k=args.top_k)
            _emit({"manifest": str(path), "summary": manifest.get("summary", {})})
            return 0
        if args.command == "open-review-queue":
            _emit(open_review_queue(args.review_manifest, limit=args.limit))
            return 0
        if args.command == "prepare-shopify-draft":
            summary, path = generate_exports(args.match_manifest, output_dir=args.output, profile="shopify")
            _emit({"manifest": str(path), "summary": summary})
            return 0
        if args.command == "request-external-action":
            path = create_approval_request(args.action, _json_object(args.payload_json), args.output)
            _emit({"request": str(path), "external_action_performed": False, "human_approval_required": True})
            return 0
        if args.command == "approve-external-action":
            path = approve_request(args.request, args.grant, args.confirm)
            _emit({"grant": str(path), "external_action_performed": False})
            return 0
        if args.command == "validate-approval":
            _emit(validate_grant(args.request, args.grant))
            return 0
        if args.command == "reserve-approved-action":
            _emit(reserve_grant(args.request, args.grant, args.state_dir))
            return 0
        if args.command == "record-execution-result":
            details = _json_object(args.details) if args.details else None
            _emit(record_execution_result(
                args.reservation,
                args.audit,
                status=args.status,
                attempt=args.attempt,
                details=details,
                external_action_performed=args.external_action_performed,
            ))
            return 0
        if args.command == "execute-shopify-stage":
            client = _shopify_client_from_env(args.store, args.api_version)
            _emit(execute_shopify_stage(args.request, args.reservation, client, audit_path=args.audit))
            return 0
        if args.command == "watch":
            watch_argv = [str(args.root), "--state", str(args.state), "--interval", str(args.interval)]
            if args.no_recursive:
                watch_argv.append("--no-recursive")
            if args.once:
                watch_argv.append("--once")
            return watch_main(watch_argv)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(f"Unsupported automation command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
