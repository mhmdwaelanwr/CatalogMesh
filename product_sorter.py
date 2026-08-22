#!/usr/bin/env python3
"""Command-line interface for the shared Product Sorter engine."""

from sorter_core import *  # preserves the public API for existing users
from sorter_core import main as cli_main


if __name__ == "__main__":
    raise SystemExit(cli_main())
