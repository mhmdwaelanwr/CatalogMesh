"""User-facing CatalogMesh branding and compatibility identifiers.

CatalogMesh is the primary product and PyPI project name. The historical
``product-sorter-*`` entry points, ``PRODUCT_SORTER_*`` environment variables and
keyring service remain supported through the v3.x line so existing scripts and
local configuration keep working.
"""
from __future__ import annotations

APP_NAME = "CatalogMesh"
APP_NAME_UPPER = "CATALOGMESH"
APP_TAGLINE = {
    "en": "AI workspace for product catalog operations",
    "ar": "مساحة عمل ذكية لعمليات كتالوج المنتجات",
    "zh": "面向商品目录运营的 AI 工作区",
}

PACKAGE_NAME = "catalogmesh"
LEGACY_PACKAGE_NAME = "ai-product-photo-sorter"
LEGACY_DISPLAY_NAME = "Product Sorter Pro"
CLI_PREFIX = "product-sorter"
ENV_PREFIX = "PRODUCT_SORTER_"
KEYRING_SERVICE = "product-sorter-pro"
