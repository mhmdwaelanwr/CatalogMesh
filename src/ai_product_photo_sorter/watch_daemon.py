from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .ingestion import IngestAsset, diff_snapshots, scan_image_folder

SNAPSHOT_SCHEMA_VERSION = 1


def _asset_from_dict(item: dict[str, Any]) -> IngestAsset:
    try:
        return IngestAsset(
            path=str(item["path"]),
            size_bytes=int(item["size_bytes"]),
            modified_ns=int(item["modified_ns"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid watched-folder snapshot asset entry") from exc


def load_snapshot(path: str | Path) -> list[IngestAsset]:
    target = Path(path).expanduser().resolve()
    if target.exists() and not target.is_file():
        raise ValueError(f"Watched-folder snapshot path is not a file: {target}")
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read watched-folder snapshot: {target}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported watched-folder snapshot format")
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("Invalid watched-folder snapshot")
    return [_asset_from_dict(item) for item in assets if isinstance(item, dict)]


def save_snapshot(path: str | Path, assets: list[IngestAsset]) -> Path:
    target = Path(path).expanduser().resolve()
    if target.exists() and not target.is_file():
        raise ValueError(f"Watched-folder snapshot path is not a file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "assets": [asset.to_dict() for asset in assets],
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return target


def watch_once(
    root: str | Path,
    snapshot_path: str | Path,
    *,
    recursive: bool = True,
) -> dict[str, list[IngestAsset]]:
    previous = load_snapshot(snapshot_path)
    current = scan_image_folder(root, recursive=recursive)
    diff = diff_snapshots(previous, current)
    save_snapshot(snapshot_path, current)
    return diff


def run_watch_daemon(
    root: str | Path,
    snapshot_path: str | Path,
    *,
    interval_seconds: float = 5.0,
    recursive: bool = True,
    on_change: Callable[[dict[str, list[IngestAsset]]], None] | None = None,
    stop_after_cycles: int | None = None,
) -> int:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    cycles = 0
    while True:
        diff = watch_once(root, snapshot_path, recursive=recursive)
        if any(diff.values()) and on_change is not None:
            on_change(diff)
        cycles += 1
        if stop_after_cycles is not None and cycles >= stop_after_cycles:
            return cycles
        time.sleep(interval_seconds)


def _print_diff(diff: dict[str, list[IngestAsset]]) -> None:
    if not any(diff.values()):
        return
    print(
        json.dumps(
            {key: [asset.to_dict() for asset in values] for key, values in diff.items()},
            ensure_ascii=False,
        ),
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch a product-shoot folder for image changes")
    parser.add_argument("root", type=Path)
    parser.add_argument("--state", type=Path, default=Path(".product-sorter-watch.json"))
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.once:
            _print_diff(watch_once(args.root, args.state, recursive=not args.no_recursive))
            return 0
        run_watch_daemon(
            args.root,
            args.state,
            interval_seconds=args.interval,
            recursive=not args.no_recursive,
            on_change=_print_diff,
        )
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
