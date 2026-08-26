"""Compatibility module for the v3.1 `model_catalog` import path."""

import sys
from ai_product_photo_sorter import model_catalog as _module

sys.modules[__name__] = _module
