"""Compatibility module for the v3.1 `providers` import path."""

import sys
from ai_product_photo_sorter import providers as _module

sys.modules[__name__] = _module
