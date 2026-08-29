"""Extra CLI safety gates around the remote Shopify layer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def apply_shopify_safety(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        try:
            if "--shopify-token" in original:
                raise SystemExit(
                    "Do not pass Shopify tokens on the command line. Store SHOPIFY_ADMIN_ACCESS_TOKEN in the OS keyring or environment instead."
                )
            if "--shopify-stage" in original:
                if "--shopify-apply" not in original:
                    raise SystemExit(
                        "Shopify staging is a remote write. Re-run with --shopify-apply after reviewing --shopify-preview output."
                    )
                sys.argv = [value for value in original if value != "--shopify-apply"]
            elif "--shopify-apply" in original:
                raise SystemExit("--shopify-apply is valid only with --shopify-stage")
            return base_parse_args(env_file)
        finally:
            sys.argv = original

    module.parse_args = parse_args
