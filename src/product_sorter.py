#!/usr/bin/env python3
"""Compatibility CLI module preserving the v3.1 `product_sorter` API."""

from sorter_core import *  # noqa: F401,F403
from sorter_core import main as cli_main

main = cli_main

if __name__ == "__main__":
    raise SystemExit(cli_main())
