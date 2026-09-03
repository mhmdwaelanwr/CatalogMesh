from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .akeneo_execution import AkeneoClient, execute_akeneo_products, reconcile_akeneo_execution
from .akeneo_rollback import execute_akeneo_rollback
from .approval_boundary import approve_request, create_approval_request, validate_grant
from .catalog_exports import generate_exports
from .connector_profiles import build_connector_plan
from .execution_control import record_execution_result, reserve_grant
from .ingestion import scan_image_folder
from .missing_assets import find_missing_assets, find_missing_local_images
from .odoo_execution import OdooClient, execute_odoo_products, reconcile_odoo_execution
from .review_automation import open_review_queue
from .shopify_execution import execute_shopify_stage
from .shopify_publication_gate import execute_shopify_publish, execute_shopify_rollback
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


def _akeneo_client_from_env(base_url: str | None = None) -> AkeneoClient:
    resolved = (base_url or os.getenv("AKENEO_BASE_URL", "")).strip()
    required = {
        "AKENEO_CLIENT_ID": os.getenv("AKENEO_CLIENT_ID", "").strip(),
        "AKENEO_CLIENT_SECRET": os.getenv("AKENEO_CLIENT_SECRET", "").strip(),
        "AKENEO_USERNAME": os.getenv("AKENEO_USERNAME", "").strip(),
        "AKENEO_PASSWORD": os.getenv("AKENEO_PASSWORD", ""),
    }
    if not resolved:
        raise ValueError("AKENEO_BASE_URL is required for Akeneo execution")
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError("Missing Akeneo environment credential(s): " + ", ".join(missing))
    return AkeneoClient(resolved, required["AKENEO_CLIENT_ID"], required["AKENEO_CLIENT_SECRET"], required["AKENEO_USERNAME"], required["AKENEO_PASSWORD"])


def _odoo_client_from_env(base_url: str | None = None, database: str | None = None) -> OdooClient:
    resolved_url = (base_url or os.getenv("ODOO_BASE_URL", "")).strip()
    resolved_db = (database or os.getenv("ODOO_DATABASE", "")).strip()
    username = os.getenv("ODOO_USERNAME", "").strip()
    api_key = os.getenv("ODOO_API_KEY", "")
    missing = [name for name, value in {"ODOO_BASE_URL": resolved_url, "ODOO_DATABASE": resolved_db, "ODOO_USERNAME": username, "ODOO_API_KEY": api_key}.items() if not value]
    if missing:
        raise ValueError("Missing Odoo environment setting(s): " + ", ".join(missing))
    return OdooClient(resolved_url, resolved_db, username, api_key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="product-sorter-automation", description="Safe local catalog-image automation commands for Product Sorter")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan"); scan.add_argument("root", type=Path); scan.add_argument("--no-recursive", action="store_true")
    missing = sub.add_parser("missing-assets"); missing.add_argument("catalog", type=Path); missing.add_argument("--sku-column", default="sku"); missing.add_argument("--asset-column", action="append", dest="asset_columns")
    missing_local = sub.add_parser("missing-local"); missing_local.add_argument("catalog", type=Path); missing_local.add_argument("shoot", type=Path); missing_local.add_argument("--sku-column", default="sku")
    propose = sub.add_parser("propose-matches"); propose.add_argument("approved_groups", type=Path); propose.add_argument("catalog", type=Path); propose.add_argument("--evidence", type=Path); propose.add_argument("--output", type=Path); propose.add_argument("--top-k", type=int, default=5)
    review = sub.add_parser("open-review-queue"); review.add_argument("review_manifest", type=Path); review.add_argument("--limit", type=int, default=50)
    draft = sub.add_parser("prepare-shopify-draft"); draft.add_argument("match_manifest", type=Path); draft.add_argument("--output", type=Path)
    connector = sub.add_parser("prepare-connector-plan"); connector.add_argument("export_manifest", type=Path); connector.add_argument("profile", type=Path); connector.add_argument("--output", type=Path)
    request = sub.add_parser("request-external-action"); request.add_argument("action"); request.add_argument("payload_json", type=Path); request.add_argument("output", type=Path)
    approve = sub.add_parser("approve-external-action"); approve.add_argument("request", type=Path); approve.add_argument("grant", type=Path); approve.add_argument("--confirm", required=True)
    validate = sub.add_parser("validate-approval"); validate.add_argument("request", type=Path); validate.add_argument("grant", type=Path)
    reserve = sub.add_parser("reserve-approved-action"); reserve.add_argument("request", type=Path); reserve.add_argument("grant", type=Path); reserve.add_argument("state_dir", type=Path)
    result = sub.add_parser("record-execution-result"); result.add_argument("reservation", type=Path); result.add_argument("audit", type=Path); result.add_argument("--status", required=True, choices=["succeeded", "failed", "cancelled"]); result.add_argument("--attempt", type=int, required=True); result.add_argument("--details", type=Path); result.add_argument("--external-action-performed", action="store_true")
    for name in ("execute-shopify-stage", "execute-shopify-publish", "execute-shopify-rollback"):
        command = sub.add_parser(name); command.add_argument("request", type=Path); command.add_argument("reservation", type=Path); command.add_argument("--audit", type=Path); command.add_argument("--store"); command.add_argument("--api-version")
    for name in ("execute-akeneo-products", "execute-akeneo-rollback"):
        command = sub.add_parser(name); command.add_argument("request", type=Path); command.add_argument("reservation", type=Path); command.add_argument("--audit", type=Path); command.add_argument("--base-url")
        if name == "execute-akeneo-products": command.add_argument("--state", type=Path)
    reconcile = sub.add_parser("reconcile-akeneo-execution"); reconcile.add_argument("state", type=Path); reconcile.add_argument("--base-url")
    odoo = sub.add_parser("execute-odoo-products"); odoo.add_argument("request", type=Path); odoo.add_argument("reservation", type=Path); odoo.add_argument("--audit", type=Path); odoo.add_argument("--state", type=Path); odoo.add_argument("--base-url"); odoo.add_argument("--database")
    odoo_reconcile = sub.add_parser("reconcile-odoo-execution"); odoo_reconcile.add_argument("state", type=Path); odoo_reconcile.add_argument("--base-url"); odoo_reconcile.add_argument("--database")
    watch = sub.add_parser("watch"); watch.add_argument("root", type=Path); watch.add_argument("--state", type=Path, default=Path(".product-sorter-watch.json")); watch.add_argument("--interval", type=float, default=5.0); watch.add_argument("--no-recursive", action="store_true"); watch.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan": _emit([item.to_dict() for item in scan_image_folder(args.root, recursive=not args.no_recursive)]); return 0
        if args.command == "missing-assets":
            kwargs: dict[str, Any] = {"sku_column": args.sku_column}
            if args.asset_columns: kwargs["asset_columns"] = tuple(args.asset_columns)
            _emit([item.to_dict() for item in find_missing_assets(_catalog_fields(args.catalog), **kwargs)]); return 0
        if args.command == "missing-local":
            images = scan_image_folder(args.shoot); _emit([item.to_dict() for item in find_missing_local_images(_catalog_fields(args.catalog), [asset.path for asset in images], sku_column=args.sku_column)]); return 0
        if args.command == "propose-matches":
            manifest, path = generate_candidates(args.approved_groups, args.catalog, evidence_json=args.evidence, output_dir=args.output, top_k=args.top_k); _emit({"manifest": str(path), "summary": manifest.get("summary", {})}); return 0
        if args.command == "open-review-queue": _emit(open_review_queue(args.review_manifest, limit=args.limit)); return 0
        if args.command == "prepare-shopify-draft":
            summary, path = generate_exports(args.match_manifest, output_dir=args.output, profile="shopify"); _emit({"manifest": str(path), "summary": summary}); return 0
        if args.command == "prepare-connector-plan":
            plan, path = build_connector_plan(args.export_manifest, args.profile, output=args.output); _emit({"plan": str(path), "plan_id": plan["plan_id"], "action": plan["action"], "records": len(plan["records"]), "network_calls_performed": 0, "human_approval_required": True}); return 0
        if args.command == "request-external-action":
            path = create_approval_request(args.action, _json_object(args.payload_json), args.output); _emit({"request": str(path), "external_action_performed": False, "human_approval_required": True}); return 0
        if args.command == "approve-external-action":
            path = approve_request(args.request, args.grant, args.confirm); _emit({"grant": str(path), "external_action_performed": False}); return 0
        if args.command == "validate-approval": _emit(validate_grant(args.request, args.grant)); return 0
        if args.command == "reserve-approved-action": _emit(reserve_grant(args.request, args.grant, args.state_dir)); return 0
        if args.command == "record-execution-result":
            details = _json_object(args.details) if args.details else None; _emit(record_execution_result(args.reservation, args.audit, status=args.status, attempt=args.attempt, details=details, external_action_performed=args.external_action_performed)); return 0
        if args.command in {"execute-shopify-stage", "execute-shopify-publish", "execute-shopify-rollback"}:
            client = _shopify_client_from_env(args.store, args.api_version)
            fn = {"execute-shopify-stage": execute_shopify_stage, "execute-shopify-publish": execute_shopify_publish, "execute-shopify-rollback": execute_shopify_rollback}[args.command]
            _emit(fn(args.request, args.reservation, client, audit_path=args.audit)); return 0
        if args.command in {"execute-akeneo-products", "execute-akeneo-rollback"}:
            client = _akeneo_client_from_env(args.base_url)
            if args.command == "execute-akeneo-products": _emit(execute_akeneo_products(args.request, args.reservation, client, audit_path=args.audit, state_path=args.state)); return 0
            _emit(execute_akeneo_rollback(args.request, args.reservation, client, audit_path=args.audit)); return 0
        if args.command == "reconcile-akeneo-execution":
            client = _akeneo_client_from_env(args.base_url); _emit(reconcile_akeneo_execution(args.state, client)); return 0
        if args.command == "execute-odoo-products":
            client = _odoo_client_from_env(args.base_url, args.database); _emit(execute_odoo_products(args.request, args.reservation, client, audit_path=args.audit, state_path=args.state)); return 0
        if args.command == "reconcile-odoo-execution":
            client = _odoo_client_from_env(args.base_url, args.database); _emit(reconcile_odoo_execution(args.state, client)); return 0
        if args.command == "watch":
            watch_argv = [str(args.root), "--state", str(args.state), "--interval", str(args.interval)]
            if args.no_recursive: watch_argv.append("--no-recursive")
            if args.once: watch_argv.append("--once")
            return watch_main(watch_argv)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(f"Unsupported automation command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
