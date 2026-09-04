"""Help adapter for the Hybrid Embeddings Shadow CLI extension.

The shadow-mode flags are consumed by the shared runtime already, but the legacy
base parser exits on ``--help`` before this extension can describe them. Keep the
execution path unchanged and add only the missing discoverability layer.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _print_help() -> None:
    print(
        "\nHybrid visual-embedding shadow mode:\n"
        "  --hybrid-embeddings                 Measure local embedding evidence; production routing stays disabled\n"
        "  --hybrid-embedding-model NAME       FastEmbed vision model\n"
        "  --hybrid-same-threshold N           Confident same-product threshold\n"
        "  --hybrid-different-threshold N      Confident different-product threshold\n"
        "  --hybrid-embedding-batch-size N     Local embedding batch size\n"
        "  --hybrid-embedding-parallel N       Optional FastEmbed parallelism\n"
        "  --hybrid-embedding-cache-dir DIR    Optional local model cache directory\n"
        "\nShadow mode records evidence only and never skips Vision calls or changes grouping."
    )


def apply_hybrid_embeddings_help(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        try:
            return base_parse_args(env_file)
        except SystemExit as exc:
            if exc.code == 0 and any(flag in sys.argv for flag in ("-h", "--help")):
                _print_help()
            raise

    module.parse_args = parse_args
