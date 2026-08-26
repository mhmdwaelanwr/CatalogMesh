"""Compatibility module for the v3.1 `secrets_store` import path."""

import sys
from ai_product_photo_sorter import secrets_store as _module

sys.modules[__name__] = _module
