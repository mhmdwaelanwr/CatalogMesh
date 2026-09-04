"""Help adapter for the standalone offline catalog-export CLI layer.

The export parser predates the chained extension help convention.  Its actions
already work, but the options were absent from ``catalogmesh --help`` because the
base parser exits before the export wrapper regains control.  Keep execution in
``catalog_exports`` and add only the missing discoverability adapter here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _print_help() -> None:
    print(
        "\nOffline catalog exports:\n"
        "  --export-catalog MANIFEST       Export a fully human-confirmed SKU manifest and exit\n"
        "  --export-output DIR             Output directory for export artifacts\n"
        "  --export-profile PROFILE        all, shopify, or pim (default all)\n"
        "\nExports remain offline: no publish or remote mutation is performed."
    )


def apply_catalog_exports_help(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        try:
            return base_parse_args(env_file)
        except SystemExit as exc:
            if exc.code == 0 and any(flag in sys.argv for flag in ("-h", "--help")):
                _print_help()
            raise

    module.parse_args = parse_args
