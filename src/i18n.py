"""Compatibility module for the v3.1 `i18n` import path."""

import sys
from ai_product_photo_sorter import i18n as _module

sys.modules[__name__] = _module
