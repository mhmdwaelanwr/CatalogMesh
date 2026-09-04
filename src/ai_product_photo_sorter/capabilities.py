"""Capability contracts used to keep CatalogMesh GUI and CLI in parity."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    id: str
    cli_command: str
    automation_command: str
    gui_surface: str
    backend_callable: str
    visual_only: bool = False


STORAGE_CAPABILITIES = (
    Capability("storage.version", "version", "storage-version", "Storage Center", "rclone_version"),
    Capability("storage.remotes", "remotes", "storage-remotes", "Storage Center", "list_remotes"),
    Capability("storage.test", "test", "storage-test", "Storage Center", "test_remote"),
    Capability("storage.dry_run", "dry-run", "storage-dry-run", "Storage Center", "stream_transfer"),
    Capability("storage.copy", "copy", "storage-copy", "Storage Center", "stream_transfer"),
    Capability("storage.sync", "sync", "storage-sync", "Storage Center", "stream_transfer"),
)


def storage_cli_commands() -> frozenset[str]:
    return frozenset(item.cli_command for item in STORAGE_CAPABILITIES)


def storage_automation_commands() -> frozenset[str]:
    return frozenset(item.automation_command for item in STORAGE_CAPABILITIES)


def storage_backend_callables() -> frozenset[str]:
    return frozenset(item.backend_callable for item in STORAGE_CAPABILITIES)
