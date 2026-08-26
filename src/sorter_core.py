"""Compatibility module for the v3.1 `sorter_core` import path."""

import sys

from ai_product_photo_sorter import core as _facade  # applies runtime path patches
from ai_product_photo_sorter import _core_impl as _module

sys.modules[__name__] = _module
