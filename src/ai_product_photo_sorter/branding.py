"""User-facing product branding kept separate from compatibility identifiers.

The Python package, console entry points and persisted environment variable names
remain ``product-sorter`` / ``PRODUCT_SORTER_*`` through the v3.x line so
existing scripts and installations continue to work.  The desktop product brand
can evolve independently.
"""
from __future__ import annotations

APP_NAME = "CatalogMesh"
APP_NAME_UPPER = "CATALOGMESH"
APP_TAGLINE = {
    "en": "AI workspace for product catalog operations",
    "ar": "مساحة عمل ذكية لعمليات كتالوج المنتجات",
    "zh": "面向商品目录运营的 AI 工作区",
}

# Compatibility identifiers are intentionally stable for v3.x.
LEGACY_DISPLAY_NAME = "Product Sorter Pro"
PACKAGE_NAME = "ai-product-photo-sorter"
CLI_PREFIX = "product-sorter"
ENV_PREFIX = "PRODUCT_SORTER_"
KEYRING_SERVICE = "product-sorter-pro"
