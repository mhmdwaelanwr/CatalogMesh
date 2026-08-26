"""Compatibility module for the v3.1 `professional` import path."""

import sys
from ai_product_photo_sorter import professional as _module

sys.modules[__name__] = _module
