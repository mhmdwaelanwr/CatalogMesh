"""Shared post-sort rclone auto-copy hook for the terminal workflow.

The desktop keeps its richer cancellable Storage UI lifecycle. The CLI uses this
hook after the core engine emits RUN_COMPLETED, so a zero exit from help, dry-run,
empty input, early exit, or an incomplete operation can never arm an upload.
Automatic transfer is always rclone copy and is never retried blindly.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Callable

from .rclone_storage import (
    RcloneError,
    TransferOptions,
    append_sync_audit,
    remote_target,
    stream_transfer,
)

_TRUE = {"1", "true", "yes", "on"}
_COPIED_OUTPUTS: set[str] = set()


def _enabled() -> bool:
    return os.getenv("PRODUCT_SORTER_RCLONE_AUTO_COPY", "").strip().lower() in _TRUE


def _desktop_manages_transfer() -> bool:
    # The Tk desktop always gives its sorter subprocess a hidden replacement-key
    # response file. That is a stable process marker and avoids duplicate auto-copy:
    # the desktop owns progress/cancel UI while terminal runs use this hook.
    return bool(os.getenv("PRODUCT_SORTER_KEY_RESPONSE_FILE", "").strip())


def _benchmark_mode() -> bool:
    return os.getenv("PRODUCT_SORTER_BENCHMARK", "").strip().lower() in _TRUE


def _status_complete(output: Path) -> bool:
    path = output / "processing_status.csv"
    if not path.is_file():
        return False
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return False
    return bool(rows) and all(str(row.get("status", "")).strip() == "completed" for row in rows)


def _target(output: Path) -> str:
    remote = os.getenv("PRODUCT_SORTER_RCLONE_REMOTE", "").strip()
    if not remote:
        raise ValueError("Automatic storage copy is enabled but no rclone remote is configured")
    base = os.getenv("PRODUCT_SORTER_RCLONE_PATH", "CatalogMesh").strip().strip("/\\")
    subpath = "/".join(part for part in (base, output.name) if part)
    return remote_target(remote, subpath)


def _options() -> TransferOptions:
    return TransferOptions(
        mode="copy",
        dry_run=False,
        bwlimit=os.getenv("PRODUCT_SORTER_RCLONE_BWLIMIT", "").strip(),
        transfers=int(os.getenv("PRODUCT_SORTER_RCLONE_TRANSFERS", "4") or "4"),
        checkers=int(os.getenv("PRODUCT_SORTER_RCLONE_CHECKERS", "8") or "8"),
    ).validated()


def auto_copy_after_success(
    output: Path | str,
    *,
    log_event: Callable[[Path, str, str], None] | None = None,
    emit: Callable[[str], None] = print,
) -> bool:
    """Copy one completed operation to rclone and return whether it succeeded."""
    if not _enabled() or _desktop_manages_transfer() or _benchmark_mode():
        return False

    output_path = Path(output).expanduser().resolve()
    key = str(output_path)
    if key in _COPIED_OUTPUTS:
        return False
    if not _status_complete(output_path):
        if log_event:
            log_event(output_path, "STORAGE_AUTO_COPY_SKIPPED", "processing_status is not fully completed")
        return False

    try:
        target = _target(output_path)
        options = _options()
    except (ValueError, OSError) as exc:
        message = f"Automatic storage copy skipped: {exc}"
        if log_event:
            log_event(output_path, "STORAGE_AUTO_COPY_FAILED", str(exc))
        emit(message)
        return False

    # Consume this automatic attempt before touching the remote. If rclone exits
    # ambiguously, do not blindly retry within the same process.
    _COPIED_OUTPUTS.add(key)
    emit(f"Automatic storage copy: {output_path} -> {target}")
    code = -1
    error = ""
    try:
        code = stream_transfer(
            output_path,
            target,
            options=options,
            on_line=emit,
        )
    except (RcloneError, OSError, ValueError) as exc:
        error = str(exc)

    try:
        append_sync_audit(
            output_path,
            target=target,
            mode="copy",
            dry_run=False,
            returncode=code,
            automatic=True,
        )
    except OSError:
        pass

    if error or code != 0:
        detail = error or f"rclone exited with code {code}"
        if log_event:
            log_event(output_path, "STORAGE_AUTO_COPY_FAILED", detail)
        emit(f"Automatic storage copy failed: {detail}")
        return False

    if log_event:
        log_event(output_path, "STORAGE_AUTO_COPY_COMPLETED", f"target={target}")
    emit("Automatic storage copy completed")
    return True


def apply_rclone_autocopy(module: Any) -> None:
    """Trigger CLI auto-copy only from the engine's real RUN_COMPLETED event."""
    if getattr(module, "_RCLONE_AUTO_COPY_INSTALLED", False):
        return
    module._RCLONE_AUTO_COPY_INSTALLED = True
    base_append_log = module.append_log

    def append_log(output: Path, event: str, message: str) -> None:
        base_append_log(output, event, message)
        if event == "RUN_COMPLETED":
            auto_copy_after_success(output, log_event=base_append_log)

    module.append_log = append_log
