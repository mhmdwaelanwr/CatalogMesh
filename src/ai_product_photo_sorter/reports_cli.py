"""Read-only CLI parity for the desktop Reports workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report_preview import discover_reports, read_report_text, report_kind


def _root(value: Path | str) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Output folder does not exist: {root}")
    return root


def _entries(root: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in discover_reports(root):
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        stat = resolved.stat()
        result.append({
            "path": relative,
            "kind": report_kind(resolved),
            "bytes": int(stat.st_size),
            "modified": float(stat.st_mtime),
        })
    return result


def _resolve_discovered(root: Path, relative: str) -> Path:
    value = str(relative or "").strip().replace("\\", "/").strip("/")
    segments = [part for part in value.split("/") if part]
    if not segments or any(part in {".", ".."} for part in segments):
        raise ValueError("Report path must be a discovered relative report path without traversal")
    wanted = "/".join(segments)
    for path in discover_reports(root):
        resolved = path.resolve()
        try:
            candidate = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        if candidate == wanted:
            return resolved
    raise ValueError(f"Report is not a discovered CatalogMesh report: {wanted}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalogmesh-reports",
        description="List and preview known CatalogMesh report artifacts without scanning arbitrary files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list")
    listing.add_argument("output", type=Path)
    listing.add_argument("--json", action="store_true")

    show = sub.add_parser("show")
    show.add_argument("output", type=Path)
    show.add_argument("report", help="Relative path exactly as shown by the list command")
    show.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = _root(args.output)
        if args.command == "list":
            reports = _entries(root)
            if args.json:
                print(json.dumps({"output": str(root), "reports": reports}, ensure_ascii=False, indent=2))
            else:
                if not reports:
                    print("No known CatalogMesh reports found")
                for item in reports:
                    print(f"{item['path']}\t{item['kind']}\t{item['bytes']} bytes")
            return 0

        if args.command == "show":
            path = _resolve_discovered(root, args.report)
            text = read_report_text(path)
            if args.json:
                print(json.dumps({
                    "output": str(root),
                    "report": path.relative_to(root).as_posix(),
                    "kind": report_kind(path),
                    "text": text,
                }, ensure_ascii=False, indent=2))
            else:
                print(text, end="" if text.endswith("\n") else "\n")
            return 0
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(f"Unsupported reports command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
