"""Safe local-first cloud output mirroring through an installed rclone binary.

This module deliberately does *not* start rclone's remote-control HTTP server and
never reads or writes the rclone configuration file.  Authentication remains
owned by rclone.  CatalogMesh invokes a narrow argv-only subprocess surface so
existing configured remotes can receive completed local output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable, Sequence


RCLONE_BIN_ENV = "PRODUCT_SORTER_RCLONE_BIN"
RCLONE_CONFIG_ENV = "PRODUCT_SORTER_RCLONE_CONFIG"
AUDIT_DIR = ".catalogmesh"
AUDIT_FILE = "storage-sync-audit.jsonl"
_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}:$")
_BWLIMIT_RE = re.compile(r"^(?:off|\d+(?:\.\d+)?(?:[KMGTP]i?B?|b)?)$", re.IGNORECASE)


class RcloneError(RuntimeError):
    """Raised for rclone discovery, validation, or execution errors."""


@dataclass(frozen=True)
class TransferOptions:
    mode: str = "copy"
    dry_run: bool = False
    transfers: int = 4
    checkers: int = 8
    bwlimit: str = ""

    def validated(self) -> "TransferOptions":
        mode = str(self.mode).strip().lower()
        if mode not in {"copy", "sync"}:
            raise ValueError("rclone transfer mode must be 'copy' or 'sync'")
        if isinstance(self.transfers, bool) or not 1 <= int(self.transfers) <= 32:
            raise ValueError("rclone transfers must be an integer from 1 to 32")
        if isinstance(self.checkers, bool) or not 1 <= int(self.checkers) <= 64:
            raise ValueError("rclone checkers must be an integer from 1 to 64")
        bwlimit = str(self.bwlimit or "").strip()
        if bwlimit and not _BWLIMIT_RE.fullmatch(bwlimit):
            raise ValueError("rclone bandwidth limit has an invalid format")
        return TransferOptions(
            mode=mode,
            dry_run=bool(self.dry_run),
            transfers=int(self.transfers),
            checkers=int(self.checkers),
            bwlimit=bwlimit,
        )


def resolve_rclone_binary() -> str:
    """Return the configured/installed rclone executable or fail clearly."""
    configured = os.environ.get(RCLONE_BIN_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        found = shutil.which(configured)
        if found:
            return found
        raise RcloneError(f"Configured rclone binary was not found: {configured}")
    found = shutil.which("rclone")
    if not found:
        raise RcloneError("rclone is not installed or is not available on PATH")
    return found


def _rclone_env() -> dict[str, str]:
    env = os.environ.copy()
    config = env.get(RCLONE_CONFIG_ENV, "").strip()
    if config:
        # rclone already understands RCLONE_CONFIG.  Mirror the app-specific
        # compatibility variable into it without ever reading the file.
        env["RCLONE_CONFIG"] = str(Path(config).expanduser())
    return env


def _capture(args: Sequence[str], *, timeout: float = 15.0) -> str:
    completed = subprocess.run(
        list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=_rclone_env(),
        shell=False,
    )
    output = completed.stdout or ""
    if completed.returncode != 0:
        message = output.strip() or f"rclone exited with code {completed.returncode}"
        raise RcloneError(message)
    return output


def rclone_version() -> str:
    output = _capture([resolve_rclone_binary(), "version"], timeout=8.0)
    return next((line.strip() for line in output.splitlines() if line.strip()), "rclone")


def list_remotes() -> tuple[str, ...]:
    """Return configured remote names without inspecting their credentials."""
    output = _capture([resolve_rclone_binary(), "listremotes"], timeout=10.0)
    remotes: list[str] = []
    for raw in output.splitlines():
        remote = raw.strip()
        if _REMOTE_NAME_RE.fullmatch(remote) and remote not in remotes:
            remotes.append(remote)
    return tuple(remotes)


def normalize_remote_name(remote: str) -> str:
    value = str(remote or "").strip()
    if value and not value.endswith(":"):
        value += ":"
    if not _REMOTE_NAME_RE.fullmatch(value):
        raise ValueError("Choose a valid configured rclone remote")
    return value


def remote_target(remote: str, subpath: str = "") -> str:
    """Build a safe rclone ``remote:path`` target from separate UI fields."""
    name = normalize_remote_name(remote)
    path = str(subpath or "").strip().replace("\\", "/").strip("/")
    if "\x00" in path or "\n" in path or "\r" in path:
        raise ValueError("Remote path contains invalid control characters")
    segments = [segment for segment in path.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError("Remote path cannot contain '.' or '..' segments")
    return name + "/".join(segments)


def remote_name_from_target(target: str) -> str:
    value = str(target or "").strip()
    if ":" not in value:
        raise ValueError("rclone destination must use remote:path syntax")
    name = value.split(":", 1)[0] + ":"
    return normalize_remote_name(name)


def test_remote(target: str) -> str:
    """Perform a read-only root listing to validate an existing remote."""
    root = remote_name_from_target(target)
    output = _capture(
        [resolve_rclone_binary(), "lsf", root, "--max-depth", "1", "--dirs-only"],
        timeout=25.0,
    )
    return output


def build_transfer_command(
    source: Path | str,
    target: str,
    *,
    options: TransferOptions | None = None,
) -> list[str]:
    """Build the exact non-shell rclone argv used for a transfer."""
    opts = (options or TransferOptions()).validated()
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_dir():
        raise ValueError(f"Local output folder does not exist: {source_path}")
    remote_name_from_target(target)

    command = [
        resolve_rclone_binary(),
        opts.mode,
        str(source_path),
        target,
        "--create-empty-src-dirs",
        "--stats", "1s",
        "--stats-one-line",
        "--log-level", "NOTICE",
        "--transfers", str(opts.transfers),
        "--checkers", str(opts.checkers),
        "--exclude", ".product_sorter.lock",
        "--exclude", "*.tmp",
    ]
    if opts.bwlimit:
        command += ["--bwlimit", opts.bwlimit]
    if opts.dry_run:
        command.append("--dry-run")
    return command


def stream_transfer(
    source: Path | str,
    target: str,
    *,
    options: TransferOptions | None = None,
    on_line: Callable[[str], None] | None = None,
    on_process: Callable[[subprocess.Popen[str]], None] | None = None,
) -> int:
    """Run one bounded transfer and stream merged output to the caller."""
    command = build_transfer_command(source, target, options=options)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=_rclone_env(),
        shell=False,
    )
    if on_process:
        on_process(process)
    if process.stdout is not None:
        for raw in process.stdout:
            line = raw.rstrip("\r\n")
            if line and on_line:
                on_line(line)
    return int(process.wait())


def append_sync_audit(
    output: Path | str,
    *,
    target: str,
    mode: str,
    dry_run: bool,
    returncode: int,
    automatic: bool,
) -> Path:
    """Append a credential-free local audit record for storage actions."""
    base = Path(output).expanduser().resolve()
    audit_dir = base / AUDIT_DIR
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / AUDIT_FILE
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": str(target),
        "mode": str(mode),
        "dry_run": bool(dry_run),
        "returncode": int(returncode),
        "automatic": bool(automatic),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path
