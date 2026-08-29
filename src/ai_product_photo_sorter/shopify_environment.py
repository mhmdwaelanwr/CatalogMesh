"""Environment Center fields and validation for guarded Shopify publishing."""

from __future__ import annotations

import re
from typing import Any

_FIELDS = (
    "SHOPIFY_STORE_DOMAIN",
    "SHOPIFY_API_VERSION",
    "SHOPIFY_PUBLICATION_ID",
)


def prepare_shopify_environment_fields(environment_module: Any) -> None:
    current = tuple(environment_module._ENV_FIELDS)
    environment_module._ENV_FIELDS = current + tuple(name for name in _FIELDS if name not in current)
    if getattr(environment_module, "_SHOPIFY_VALIDATION_INSTALLED", False):
        return
    base_validate = environment_module._validate_setting

    def validate_setting(name: str, value: str) -> str:
        value = base_validate(name, value)
        if name == "SHOPIFY_STORE_DOMAIN" and value:
            normalized = re.sub(r"^https?://", "", value.strip().lower()).rstrip("/")
            if "/" in normalized or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", normalized):
                raise ValueError("SHOPIFY_STORE_DOMAIN must look like store-name.myshopify.com")
            return normalized
        if name == "SHOPIFY_API_VERSION" and value:
            if not re.fullmatch(r"20\d{2}-(?:01|04|07|10)", value):
                raise ValueError("SHOPIFY_API_VERSION must use Shopify's YYYY-MM quarterly format")
            return value
        if name == "SHOPIFY_PUBLICATION_ID" and value:
            if not re.fullmatch(r"gid://shopify/Publication/\d+", value):
                raise ValueError("SHOPIFY_PUBLICATION_ID must be a Shopify Publication GID")
            return value
        return value

    environment_module._validate_setting = validate_setting
    environment_module._SHOPIFY_VALIDATION_INSTALLED = True
