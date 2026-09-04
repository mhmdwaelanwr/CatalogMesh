"""Capability contracts used to keep CatalogMesh GUI and CLI in parity."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    id: str
    cli_command: str
    gui_surface: str
    visual_only: bool = False


STORAGE_CAPABILITIES = (
    Capability("storage.version", "storage-version", "Storage Center"),
    Capability("storage.remotes", "storage-remotes", "Storage Center"),
    Capability("storage.test", "storage-test", "Storage Center"),
    Capability("storage.dry_run", "storage-dry-run", "Storage Center"),
    Capability("storage.copy", "storage-copy", "Storage Center"),
    Capability("storage.sync", "storage-sync", "Storage Center"),
)


def storage_cli_commands() -> frozenset[str]:
    return frozenset(item.cli_command for item in STORAGE_CAPABILITIES)
