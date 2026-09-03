from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}


@dataclass(frozen=True)
class IngestAsset:
    path: str
    size_bytes: int
    modified_ns: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def scan_image_folder(root: str | Path, *, recursive: bool = True) -> list[IngestAsset]:
    """Build a deterministic snapshot of image files without mutating them."""
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(base)
    if not base.is_dir():
        raise NotADirectoryError(base)

    iterator: Iterable[Path] = base.rglob("*") if recursive else base.iterdir()
    assets: list[IngestAsset] = []
    for path in iterator:
        if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
            continue
        stat = path.stat()
        assets.append(
            IngestAsset(
                path=str(path),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
            )
        )
    return sorted(assets, key=lambda asset: asset.path.casefold())


def diff_snapshots(
    previous: Iterable[IngestAsset], current: Iterable[IngestAsset]
) -> dict[str, list[IngestAsset]]:
    """Return added, changed, and removed files between two folder snapshots."""
    old = {asset.path: asset for asset in previous}
    new = {asset.path: asset for asset in current}
    added = [new[path] for path in new.keys() - old.keys()]
    removed = [old[path] for path in old.keys() - new.keys()]
    changed = [
        new[path]
        for path in new.keys() & old.keys()
        if (new[path].size_bytes, new[path].modified_ns)
        != (old[path].size_bytes, old[path].modified_ns)
    ]
    sort_key = lambda asset: asset.path.casefold()
    return {
        "added": sorted(added, key=sort_key),
        "changed": sorted(changed, key=sort_key),
        "removed": sorted(removed, key=sort_key),
    }
