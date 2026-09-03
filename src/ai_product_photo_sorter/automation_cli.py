from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .catalog_exports import generate_exports
from .ingestion import scan_image_folder
from .missing_assets import find_missing_assets, find_missing_local_images
from .sku_matching import generate_candidates, load_catalog_rows
from .watch_daemon import main as watch_main


def _catalog_fields(path: Path) -> list[dict[str, Any]]:
    return [dict(row.get("fields", {})) for row in load_catalog_rows(path)]


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


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

    draft = sub.add_parser("prepare-shopify-draft", help="Prepare an offline Shopify draft from fully human-confirmed SKU matches")
    draft.add_argument("match_manifest", type=Path)
    draft.add_argument("--output", type=Path)

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
        if args.command == "prepare-shopify-draft":
            summary, path = generate_exports(args.match_manifest, output_dir=args.output, profile="shopify")
            _emit({"manifest": str(path), "summary": summary})
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
