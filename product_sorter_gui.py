#!/usr/bin/env python3
"""Source-checkout compatibility launcher for the Product Sorter desktop app."""

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if __name__ == "__main__" and "--cli-worker" in sys.argv:
    sys.argv.remove("--cli-worker")
    from ai_product_photo_sorter.core import main as _cli_main
    raise SystemExit(_cli_main())

from ai_product_photo_sorter.gui import *  # noqa: F401,F403,E402
from ai_product_photo_sorter.gui import main  # noqa: E402


if __name__ == "__main__":
    main()
