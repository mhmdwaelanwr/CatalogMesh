from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_ASSET_COLUMNS = ("image", "images", "image_url", "image_urls", "photo", "photos")


@dataclass(frozen=True)
class MissingAsset:
    row_number: int
    sku: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def find_missing_assets(
    rows: Iterable[Mapping[str, object]],
    *,
    sku_column: str = "sku",
    asset_columns: Sequence[str] = DEFAULT_ASSET_COLUMNS,
) -> list[MissingAsset]:
    """Return catalog rows that have a SKU but no usable image reference.

    Matching is intentionally deterministic and offline. A row is considered to
    have an asset when any configured asset column contains non-whitespace text.
    Rows without a SKU are ignored because they cannot be safely actionable.
    """
    missing: list[MissingAsset] = []
    normalized_assets = tuple(column.strip() for column in asset_columns if column.strip())
    if not normalized_assets:
        raise ValueError("asset_columns must contain at least one column")

    for row_number, row in enumerate(rows, start=2):
        sku = _text(row.get(sku_column))
        if not sku:
            continue
        if any(_text(row.get(column)) for column in normalized_assets):
            continue
        missing.append(MissingAsset(row_number=row_number, sku=sku, reason="no_asset_reference"))
    return missing


def image_files_by_stem(paths: Iterable[str | Path]) -> set[str]:
    """Return case-folded image stems for local shoot/catalog reconciliation."""
    extensions = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
    return {
        Path(path).stem.casefold()
        for path in paths
        if Path(path).suffix.casefold() in extensions
    }


def find_missing_local_images(
    rows: Iterable[Mapping[str, object]],
    image_paths: Iterable[str | Path],
    *,
    sku_column: str = "sku",
) -> list[MissingAsset]:
    """Find SKUs that do not have a same-stem local image candidate.

    This is a conservative preflight helper, not an automatic SKU matcher. It
    deliberately avoids fuzzy matching so ambiguous catalog writes remain gated
    behind the existing review and confirmation workflow.
    """
    stems = image_files_by_stem(image_paths)
    missing: list[MissingAsset] = []
    for row_number, row in enumerate(rows, start=2):
        sku = _text(row.get(sku_column))
        if sku and sku.casefold() not in stems:
            missing.append(MissingAsset(row_number=row_number, sku=sku, reason="no_local_image_candidate"))
    return missing
