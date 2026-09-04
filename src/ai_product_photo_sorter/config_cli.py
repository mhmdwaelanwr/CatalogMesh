"""Bounded CLI parity for the desktop Environment workspace.

This command deliberately exposes only the documented CatalogMesh settings. It
is not a generic environment-variable executor and never prints secret values.
Sensitive values are accepted only through an interactive hidden prompt so they
do not land in shell history.
"""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .environment_gui import _ENV_FIELDS, _SENSITIVE, _mask_value, _validate_setting
from .secrets_store import SECRET_NAMES, clear as clear_keyring, read as read_keyring
from . import setup_wizard


def _path() -> Path:
    return Path(setup_wizard.ENV_FILE).expanduser().resolve()


def _read() -> dict[str, str]:
    values = setup_wizard.read_env(_path())
    use_keyring = str(values.get("USE_KEYRING", "")).strip().lower() in {
        "1", "true", "yes", "on"
    }
    # Shopify is always keyring-only; AI keys join when USE_KEYRING is enabled.
    stored = read_keyring()
    for name, value in stored.items():
        if value and (name == "SHOPIFY_ADMIN_ACCESS_TOKEN" or use_keyring) and not values.get(name):
            values[name] = value
    return values


def _write(values: dict[str, str]) -> None:
    setup_wizard.save_env(values, _path())


def _require_name(name: str) -> str:
    value = str(name or "").strip()
    if value not in _ENV_FIELDS:
        raise ValueError(f"Unknown CatalogMesh setting: {value}")
    return value


def _public_snapshot(values: dict[str, str]) -> dict[str, str]:
    return {
        name: _mask_value(name, str(values.get(name, "")))
        for name in _ENV_FIELDS
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalogmesh-config",
        description="Manage the same bounded CatalogMesh settings exposed by the desktop Environment workspace.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="List supported settings with secrets masked")
    listing.add_argument("--json", action="store_true")

    get = sub.add_parser("get", help="Show one setting; secret values remain masked")
    get.add_argument("name")
    get.add_argument("--json", action="store_true")

    set_value = sub.add_parser("set", help="Set one non-secret setting")
    set_value.add_argument("name")
    set_value.add_argument("value")

    set_secret = sub.add_parser("set-secret", help="Set one secret using a hidden interactive prompt")
    set_secret.add_argument("name")

    unset = sub.add_parser("unset", help="Clear one setting")
    unset.add_argument("name")

    clear_keys = sub.add_parser("clear-api-keys", help="Clear all API credentials from .env and keyring")
    clear_keys.add_argument("--confirm", required=True, metavar="PHRASE")

    delete = sub.add_parser("delete", help="Delete the CatalogMesh .env and clear stored credentials")
    delete.add_argument("--confirm", required=True, metavar="PHRASE")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            snapshot = _public_snapshot(_read())
            if args.json:
                print(json.dumps({"settings": snapshot, "config_file": str(_path())}, ensure_ascii=False, indent=2))
            else:
                print(f"CatalogMesh configuration: {_path()}")
                for name, value in snapshot.items():
                    print(f"{name}={value}")
            return 0

        if args.command == "get":
            name = _require_name(args.name)
            value = _mask_value(name, str(_read().get(name, "")))
            if args.json:
                print(json.dumps({"name": name, "value": value, "config_file": str(_path())}, ensure_ascii=False, indent=2))
            else:
                print(f"{name}={value}")
            return 0

        if args.command == "set":
            name = _require_name(args.name)
            if name in _SENSITIVE:
                raise ValueError("Secret values cannot be passed on the command line; use set-secret instead")
            values = _read()
            values[name] = _validate_setting(name, args.value)
            _write(values)
            print(f"Updated {name}")
            return 0

        if args.command == "set-secret":
            name = _require_name(args.name)
            if name not in _SENSITIVE:
                raise ValueError("set-secret accepts only credential settings")
            value = getpass.getpass(f"{name}: ").strip()
            if not value:
                raise ValueError("Secret value cannot be blank; use unset to clear it")
            values = _read()
            values[name] = _validate_setting(name, value)
            _write(values)
            print(f"Updated {name}; value was not printed")
            return 0

        if args.command == "unset":
            name = _require_name(args.name)
            values = _read()
            values[name] = ""
            if name in _SENSITIVE:
                clear_keyring((name,))
            _write(values)
            print(f"Cleared {name}")
            return 0

        if args.command == "clear-api-keys":
            expected = "CLEAR API KEYS"
            if args.confirm != expected:
                raise ValueError(f"Credential clearing requires the exact confirmation: {expected}")
            values = _read()
            for name in SECRET_NAMES:
                values[name] = ""
            clear_keyring()
            _write(values)
            print("Cleared CatalogMesh API credentials from configuration and OS keyring")
            return 0

        if args.command == "delete":
            expected = f"DELETE CONFIG {_path()}"
            if args.confirm != expected:
                raise ValueError(f"Configuration deletion requires the exact confirmation: {expected}")
            _path().unlink(missing_ok=True)
            clear_keyring()
            print(f"Deleted CatalogMesh configuration: {_path()}")
            return 0
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(f"Unsupported configuration command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
