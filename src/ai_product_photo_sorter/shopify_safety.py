"""Extra CLI safety gates around the remote Shopify layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .shopify_publishing import build_plan

PLAN_NAME = "shopify_publish_plan.json"


def _value_after(argv: list[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
        raise SystemExit(f"{flag} requires a value")
    return argv[index + 1]


def apply_shopify_safety(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        try:
            if "--shopify-token" in original:
                raise SystemExit(
                    "Do not pass Shopify tokens on the command line. Store SHOPIFY_ADMIN_ACCESS_TOKEN in the OS keyring or environment instead."
                )
            if "--shopify-plan" in original:
                source_raw = _value_after(original, "--shopify-plan")
                source = Path(str(source_raw)).expanduser().resolve()
                output_raw = _value_after(original, "--shopify-output") if "--shopify-output" in original else None
                destination = (
                    Path(output_raw).expanduser().resolve()
                    if output_raw
                    else source.parent / "shopify_remote"
                )
                destination.mkdir(parents=True, exist_ok=True)
                plan = build_plan(source)
                path = destination / PLAN_NAME
                path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"Shopify local plan: {path}")
                print(
                    f"Products: {plan['source_products']} · remote reads: 0 · remote writes: 0 · inventory writes: 0"
                )
                raise SystemExit(0)
            if "--shopify-stage" in original:
                if "--shopify-apply" not in original:
                    raise SystemExit(
                        "Shopify staging is a remote write. Re-run with --shopify-apply after reviewing --shopify-plan and --shopify-preview output."
                    )
                sys.argv = [value for value in original if value != "--shopify-apply"]
            elif "--shopify-apply" in original:
                raise SystemExit("--shopify-apply is valid only with --shopify-stage")
            return base_parse_args(env_file)
        except (ValueError, OSError) as exc:
            raise SystemExit(str(exc)) from exc
        finally:
            sys.argv = original

    module.parse_args = parse_args
