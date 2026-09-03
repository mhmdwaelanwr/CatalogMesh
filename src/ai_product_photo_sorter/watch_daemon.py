from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .ingestion import IngestAsset, diff_snapshots, scan_image_folder

SNAPSHOT_SCHEMA_VERSION = 1


def _asset_from_dict(item: dict[str, Any]) -> IngestAsset:
    return IngestAsset(path=str(item["path"]), size_bytes=int(item["size_bytes"]), modified_ns=int(item["modified_ns"]))


def load_snapshot(path: str | Path) -> list[IngestAsset]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return []
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported watched-folder snapshot format")
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("Invalid watched-folder snapshot")
    return [_asset_from_dict(item) for item in assets if isinstance(item, dict)]


def save_snapshot(path: str | Path, assets: list[IngestAsset]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SNAPSHOT_SCHEMA_VERSION, "assets": [asset.to_dict() for asset in assets]}
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def watch_once(root: str | Path, snapshot_path: str | Path, *, recursive: bool = True) -> dict[str, list[IngestAsset]]:
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
    print(json.dumps({key: [asset.to_dict() for asset in values] for key, values in diff.items()}, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch a product-shoot folder for image changes")
    parser.add_argument("root", type=Path)
    parser.add_argument("--state", type=Path, default=Path(".product-sorter-watch.json"))
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.once:
        _print_diff(watch_once(args.root, args.state, recursive=not args.no_recursive))
        return 0
    try:
        run_watch_daemon(args.root, args.state, interval_seconds=args.interval, recursive=not args.no_recursive, on_change=_print_diff)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
