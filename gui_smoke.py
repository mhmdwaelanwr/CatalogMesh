#!/usr/bin/env python3
"""Compatibility launcher for the organized GUI smoke test."""

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.smoke.gui_smoke import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
