"""Compatibility module for the v3.1 `set_data` import path."""

from ai_product_photo_sorter.setup_wizard import *  # noqa: F401,F403
from ai_product_photo_sorter.setup_wizard import main


if __name__ == "__main__":
    raise SystemExit(main())
