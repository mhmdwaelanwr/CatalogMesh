from __future__ import annotations

import os

SERVICE = "product-sorter-pro"
AI_SECRET_NAMES = tuple(
    f"{provider}_API_KEY_{i}"
    for provider in ("GEMINI", "OPENAI", "ANTHROPIC")
    for i in range(1, 5)
)
SECRET_NAMES = (*AI_SECRET_NAMES, "SHOPIFY_ADMIN_ACCESS_TOKEN")


def save(values: dict[str, str]) -> bool:
    try:
        import keyring

        for name in SECRET_NAMES:
            if values.get(name):
                keyring.set_password(SERVICE, name, values[name])
        return True
    except Exception:
        return False


def read() -> dict[str, str]:
    """Return configured keyring secrets without exposing them in logs."""
    try:
        import keyring

        result: dict[str, str] = {}
        for name in SECRET_NAMES:
            value = keyring.get_password(SERVICE, name)
            if value:
                result[name] = value
        return result
    except Exception:
        return {}


def clear(names: tuple[str, ...] = SECRET_NAMES) -> bool:
    """Best-effort removal of Product Sorter credentials from the OS keyring."""
    try:
        import keyring
        from keyring.errors import PasswordDeleteError
    except Exception:
        return False

    available = True
    for name in names:
        try:
            keyring.delete_password(SERVICE, name)
        except PasswordDeleteError:
            # Missing is already the desired final state.
            pass
        except Exception:
            available = False
    return available


def load_into_environment() -> bool:
    try:
        for name, value in read().items():
            os.environ.setdefault(name, value)
        return True
    except Exception:
        return False
