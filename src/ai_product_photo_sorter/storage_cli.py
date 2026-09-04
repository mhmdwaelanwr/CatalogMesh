"""First-class bounded rclone Storage CLI for CatalogMesh."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

from .rclone_storage import (
    RcloneError,
    TransferOptions,
    append_sync_audit,
    build_transfer_command,
    list_remotes,
    rclone_version,
    stream_transfer,
    remote_target,
    test_remote,
)


def validate_remote_target(target: str) -> str:
    """Validate a complete remote:path target through the shared path builder."""
    value = str(target or "").strip()
    if ":" not in value:
        raise ValueError("rclone destination must use remote:path syntax")
    remote, subpath = value.split(":", 1)
    return remote_target(remote + ":", subpath)


def _add_json_flag(parser: argparse.ArgumentParser, *, root: bool = False) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        default=False if root else argparse.SUPPRESS,
        help="Emit one machine-readable JSON result instead of human-readable output.",
    )


def _add_transfer_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bwlimit", default="", help="rclone bandwidth limit, for example 10M.")
    parser.add_argument("--transfers", type=int, default=4)
    parser.add_argument("--checkers", type=int, default=8)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalogmesh-storage",
        description="Bounded rclone storage commands for CatalogMesh.",
    )
    _add_json_flag(parser, root=True)
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Show the installed rclone version.")
    _add_json_flag(version)

    remotes = sub.add_parser("remotes", help="List configured rclone remotes.")
    _add_json_flag(remotes)

    test = sub.add_parser("test", help="Test read-only connectivity to a remote.")
    test.add_argument("target", help="Validated rclone target such as gdrive:CatalogMesh.")
    _add_json_flag(test)

    dry_run = sub.add_parser("dry-run", help="Preview a copy or sync without mutating the remote.")
    dry_run.add_argument("source", type=Path)
    dry_run.add_argument("target")
    dry_run.add_argument("--mode", choices=("copy", "sync"), default="copy")
    _add_transfer_options(dry_run)
    _add_json_flag(dry_run)

    copy = sub.add_parser("copy", help="Copy local output without deleting remote-only files.")
    copy.add_argument("source", type=Path)
    copy.add_argument("target")
    _add_transfer_options(copy)
    _add_json_flag(copy)

    sync = sub.add_parser("sync", help="Mirror local output and allow deletion of remote-only files.")
    sync.add_argument("source", type=Path)
    sync.add_argument("target")
    sync.add_argument(
        "--confirm",
        default="",
        metavar="PHRASE",
        help='Required exact target-specific phrase: "SYNC <full-target>".',
    )
    _add_transfer_options(sync)
    _add_json_flag(sync)
    return parser


def _emit(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return

    command = payload.get("command")
    if command == "version":
        print(payload["version"])
    elif command == "remotes":
        remotes = payload["remotes"]
        if remotes:
            for remote in remotes:
                print(remote)
        else:
            print("No configured rclone remotes found.")
    elif command == "test":
        print(f"OK {payload['target']}")
        listing = str(payload.get("listing") or "").strip()
        if listing:
            print(listing)
    elif command in {"dry-run", "copy", "sync"}:
        status = "completed" if payload.get("returncode") == 0 else "failed"
        print(
            f"{command.upper()} {status}: "
            f"{payload.get('source')} -> {payload.get('target')}"
        )


def _transfer(args: argparse.Namespace, *, mode: str, dry_run: bool) -> int:
    source = Path(args.source).expanduser()
    target = validate_remote_target(args.target)
    options = TransferOptions(
        mode=mode,
        dry_run=dry_run,
        transfers=args.transfers,
        checkers=args.checkers,
        bwlimit=args.bwlimit,
    ).validated()
    if mode == "sync" and not dry_run:
        expected = f"SYNC {target}"
        if str(getattr(args, "confirm", "")) != expected:
            raise ValueError(
                "Destructive sync requires the exact target-specific confirmation: "
                f"{expected}"
            )

    command = build_transfer_command(source, target, options=options)

    lines: list[str] = []
    process_holder: dict[str, subprocess.Popen[str]] = {}

    def on_line(line: str) -> None:
        lines.append(line)
        if not args.json:
            print(line)

    def on_process(process: subprocess.Popen[str]) -> None:
        process_holder["process"] = process

    try:
        returncode = stream_transfer(
            source,
            target,
            options=options,
            on_line=on_line,
            on_process=on_process,
        )
    except KeyboardInterrupt:
        process = process_holder.get("process")
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                try:
                    process.kill()
                except OSError:
                    pass
        if args.json:
            _emit(
                {
                    "command": args.command,
                    "mode": mode,
                    "dry_run": dry_run,
                    "source": str(source.resolve()),
                    "target": target,
                    "returncode": 130,
                    "cancelled": True,
                    "output": lines,
                },
                json_output=True,
            )
        else:
            print("Transfer cancelled.")
        return 130

    try:
        append_sync_audit(
            source,
            target=target,
            mode=mode,
            dry_run=dry_run,
            returncode=returncode,
            automatic=False,
        )
    except OSError:
        pass

    payload = {
        "command": args.command,
        "mode": mode,
        "dry_run": dry_run,
        "source": str(source.resolve()),
        "target": target,
        "argv": command,
        "returncode": returncode,
        "output": lines,
    }
    _emit(payload, json_output=bool(args.json))
    if returncode != 0:
        raise RcloneError(
            "\n".join(lines).strip() or f"rclone exited with code {returncode}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "version":
            _emit(
                {"command": "version", "version": rclone_version()},
                json_output=bool(args.json),
            )
            return 0
        if args.command == "remotes":
            _emit(
                {"command": "remotes", "remotes": list(list_remotes())},
                json_output=bool(args.json),
            )
            return 0
        if args.command == "test":
            target = validate_remote_target(args.target)
            listing = test_remote(target)
            _emit(
                {
                    "command": "test",
                    "target": target,
                    "reachable": True,
                    "listing": listing,
                },
                json_output=bool(args.json),
            )
            return 0
        if args.command == "dry-run":
            return _transfer(args, mode=args.mode, dry_run=True)
        if args.command == "copy":
            return _transfer(args, mode="copy", dry_run=False)
        if args.command == "sync":
            return _transfer(args, mode="sync", dry_run=False)
    except (ValueError, OSError, RcloneError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(f"Unsupported storage command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
