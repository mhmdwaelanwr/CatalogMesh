#!/usr/bin/env python3
"""Source-checkout compatibility launcher for guided configuration."""

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_product_photo_sorter.setup_wizard import *  # noqa: F401,F403,E402
from ai_product_photo_sorter.setup_wizard import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
