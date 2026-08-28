"""Production hardening for large retail photo collections.

This module keeps the v3.1 engine stable while applying narrowly scoped runtime
improvements that are useful for long-running, real-world catalog jobs:

* safer handling of very high-resolution phone/camera JPEGs;
* a broader retail-technology category taxonomy;
* independent copy outputs by default, with an opt-in zero-copy reference mode;
* output materialization that survives cross-volume and Windows link failures;
* managed-output cleanup so rebuilds do not leave stale duplicate links behind.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import threading
from collections import Counter
from pathlib import Path
from typing import Any


# Modern phone cameras can legitimately produce 100 MP+ JPEG files. Pillow's
# default warning threshold is lower than that on many releases. We raise the
# finite warning threshold rather than disabling decompression-bomb protection.
MAX_TRUSTED_IMAGE_PIXELS = 200_000_000
API_IMAGE_EDGE = 1600
API_JPEG_QUALITY = 82
MANIFEST_NAME = ".product-sorter-managed-outputs.json"
OUTPUT_MODE_ENV = "PRODUCT_SORTER_OUTPUT_MODE"
DEFAULT_OUTPUT_MODE = "copy"
OUTPUT_MODES = {"copy", "auto", "hardlink", "symlink"}
COPY_RESERVE_BYTES = 512 * 1024 * 1024
_TRUNCATED_IMAGE_LOCK = threading.Lock()

RETAIL_CATEGORIES = {
    "adapter",
    "cable",
    "case",
    "charger",
    "controller",
    "earbuds",
    "headset",
    "hub",
    "keyboard",
    "lighting",
    "microphone",
    "mouse",
    "networking",
    "power_bank",
    "screen_protector",
    "smartwatch",
    "speaker",
    "stand",
    "storage",
    "tool",
    "webcam",
    "other",
}


def _compressed_image_bytes(module: Any, path: Path) -> bytes:
    """Create a bounded JPEG payload without decoding huge JPEGs at full size.

    ``draft`` lets Pillow ask the JPEG decoder for a lower-resolution decode
    before EXIF transpose/conversion. It is only a hint, so the normal thumbnail
    step remains the final size guarantee for every supported JPEG.
    """

    Image = module.Image
    ImageOps = module.ImageOps
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required before product images can be processed")

    def encode() -> bytes:
        with Image.open(path) as original:
            # JPEG supports decoder-level downsampling through draft(). Other
            # image types ignore or reject the hint.
            try:
                original.draft("RGB", (API_IMAGE_EDGE, API_IMAGE_EDGE))
            except (AttributeError, ValueError):
                pass

            working = ImageOps.exif_transpose(original)
            try:
                if working.mode != "RGB":
                    converted = working.convert("RGB")
                    if working is not original:
                        working.close()
                    working = converted
                working.thumbnail((API_IMAGE_EDGE, API_IMAGE_EDGE), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                working.save(
                    buffer,
                    format="JPEG",
                    quality=API_JPEG_QUALITY,
                    optimize=True,
                )
                return buffer.getvalue()
            finally:
                if working is not original:
                    working.close()

    try:
        return encode()
    except OSError as exc:
        if "truncated" not in str(exc).lower():
            raise OSError(f"Cannot decode product image '{path.name}': {exc}") from exc

    # Some cameras/transfer tools leave a usable JPEG without its complete end
    # marker. Pillow can recover those pixels explicitly. The setting is global,
    # so protect and restore it even though image encoding is currently serial.
    from PIL import ImageFile

    with _TRUNCATED_IMAGE_LOCK:
        previous = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            return encode()
        except OSError as exc:
            raise OSError(
                f"Cannot recover truncated product image '{path.name}': {exc}"
            ) from exc
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous


def _prompt_for(module: Any, photos: list[Any], catalog: str) -> str:
    listing = "\n".join(
        f"Image {index}: {photo.path.name}, captured {photo.taken_at.isoformat(sep=' ')}"
        for index, photo in enumerate(photos, 1)
    )
    catalog_text = f"\nPossible catalog rows:\n{catalog}" if catalog else ""
    categories = "|".join(sorted(module.CATEGORIES))
    return f"""You classify consecutive photos from a retail technology store photo shoot.
Each product was usually photographed from the front and then the back, but a
product may have one, two, or more photos. Use object appearance, packaging,
brand/model text, accessories visible in the package, and capture time. Never
assume strict pairs.

{listing}
{catalog_text}

Return JSON only in this exact shape:
{{"items":[{{"filename":"exact filename","same_product_as_previous":false,
"category":"{categories}",
"view":"front|back|side|detail|unknown","brand":"", "model":"",
"catalog_match":"", "confidence":0.0, "reason":"short reason"}}]}}

Rules:
- Include every image exactly once and preserve the listed order.
- For the first image, same_product_as_previous must be false.
- Confidence is from 0 to 1.
- Read visible package text carefully; do not invent a model number.
- Prefer a concrete category over 'other' whenever the product type is visible.
- catalog_match must be an exact catalog row or empty.
"""


def _output_mode() -> str:
    mode = os.getenv(OUTPUT_MODE_ENV, DEFAULT_OUTPUT_MODE).strip().lower() or DEFAULT_OUTPUT_MODE
    if mode not in OUTPUT_MODES:
        allowed = ", ".join(sorted(OUTPUT_MODES))
        raise RuntimeError(f"Invalid {OUTPUT_MODE_ENV}={mode!r}; choose one of: {allowed}")
    return mode


def _managed_relative_path(output: Path, destination: Path) -> str:
    return destination.relative_to(output).as_posix()


def _safe_manifest_target(output: Path, relative: str) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return output.joinpath(candidate)


def _remove_previous_managed_outputs(output: Path) -> None:
    """Remove only files created/adopted by a previous hardened build.

    User-created files inside the output tree are deliberately left alone.
    Empty product/category directories are removed opportunistically afterwards.
    """

    manifest_path = output / MANIFEST_NAME
    if not manifest_path.is_file():
        return
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = payload.get("files", []) if isinstance(payload, dict) else []
    except (OSError, json.JSONDecodeError):
        return

    touched_parents: set[Path] = set()
    for entry in entries:
        # Schema 1 stored strings. Schema 2 stores {path, mode} objects.
        relative = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(relative, str):
            continue
        target = _safe_manifest_target(output, relative)
        if target is None:
            continue
        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
                touched_parents.add(target.parent)
        except OSError:
            # A stale file should not make the whole catalog unrebuildable.
            continue

    # Work deepest-first and stop at the operation root. rmdir only succeeds on
    # empty directories, so manually added files are never removed.
    candidates: set[Path] = set()
    for parent in touched_parents:
        current = parent
        while current != output and output in current.parents:
            candidates.add(current)
            current = current.parent
    for directory in sorted(candidates, key=lambda value: len(value.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _collision_safe_destination(destination: Path, source: Path) -> tuple[Path, bool]:
    """Never overwrite or adopt an unrelated file at a generated destination.

    Returns ``(path, existing_same_source)``. Legacy hardlinks/symlinks that
    already point to the source can be safely adopted; unrelated files are left
    untouched and the generated output gets a deterministic ``__sorter_N`` name.
    """

    if not os.path.lexists(destination):
        return destination, False
    if _same_file(destination, source):
        return destination, True

    for index in range(1, 10_000):
        candidate = destination.with_name(
            f"{destination.stem}__sorter_{index}{destination.suffix}"
        )
        if not os.path.lexists(candidate):
            return candidate, False
        if _same_file(candidate, source):
            return candidate, True
    raise RuntimeError(f"Could not find a safe output filename for {destination.name}")


def _materialize(source: Path, destination: Path, mode: str | None = None) -> str:
    """Expose an original in the catalog without modifying the source.

    ``copy`` is the safe default because the catalog file is independent and can
    be edited later without changing the source photo. ``auto`` preserves the
    historical zero-copy preference: hardlink, then symlink, then copy fallback.
    Explicit ``hardlink``/``symlink`` modes fail clearly if unsupported instead
    of silently changing storage semantics.
    """

    selected = mode or _output_mode()
    if selected == "copy":
        shutil.copy2(source, destination)
        return "copy"
    if selected == "hardlink":
        try:
            os.link(source, destination)
        except OSError as exc:
            raise RuntimeError(f"Could not create hardlink for {source.name}: {exc}") from exc
        return "hardlink"
    if selected == "symlink":
        try:
            destination.symlink_to(source.resolve())
        except OSError as exc:
            raise RuntimeError(f"Could not create symlink for {source.name}: {exc}") from exc
        return "symlink"

    # auto: retain the previous disk-saving behavior, but always finish with a
    # real copy when links are unavailable (common on Windows/cross-volume runs).
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        pass
    try:
        destination.symlink_to(source.resolve())
        return "symlink"
    except OSError:
        try:
            if destination.is_symlink() or os.path.lexists(destination):
                destination.unlink()
        except OSError:
            pass
    shutil.copy2(source, destination)
    return "copy"


def _copy_bytes_required(items: list[dict[str, Any]]) -> int:
    seen: set[Path] = set()
    total = 0
    for item in items:
        path = Path(item["path"])
        try:
            identity = path.resolve()
        except OSError:
            identity = path.absolute()
        if identity in seen:
            continue
        seen.add(identity)
        total += path.stat().st_size
    return total


def _ensure_copy_capacity(items: list[dict[str, Any]], output: Path) -> None:
    """Fail before copying when there is clearly not enough destination space."""

    required = _copy_bytes_required(items)
    if required <= 0:
        return
    free = shutil.disk_usage(output).free
    reserve = max(COPY_RESERVE_BYTES, int(required * 0.05))
    if free < required + reserve:
        gib = 1024 ** 3
        raise RuntimeError(
            "Not enough free space for independent catalog copies: "
            f"need about {required / gib:.2f} GiB plus reserve, "
            f"but only {free / gib:.2f} GiB is free. Free disk space or set "
            f"{OUTPUT_MODE_ENV}=auto for disk-saving links (do not edit linked "
            "catalog images if you need the source originals to remain byte-identical)."
        )


def _write_json_atomic(path: Path, payload: Any) -> None:
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _build_outputs(
    module: Any,
    items: list[dict[str, Any]],
    output: Path,
    confidence: float,
    dry_run: bool,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "classification_report.csv"
    selected_mode = _output_mode()

    if not dry_run:
        # Clear only files tracked by the program. Cached AI results remain in
        # SQLite, so an out-of-space error never requires paying for analysis again.
        _remove_previous_managed_outputs(output)
        if selected_mode == "copy":
            _ensure_copy_capacity(items, output)

    product_number = 0
    current_folder = ""
    rows: list[dict[str, Any]] = []
    managed_files: list[dict[str, str]] = []
    materialization_modes: Counter[str] = Counter()

    for index, item in enumerate(items):
        if index == 0 or not item["same_product_as_previous"]:
            product_number += 1
            label = "_".join(value for value in (item["brand"], item["model"]) if value)
            current_folder = (
                f"Product_{product_number:04d}_{module.safe_name(label, item['category'])}"
            )

        review = item["confidence"] < confidence or item["category"] == "other"
        destination_dir = output / ("Needs_Review" if review else item["category"]) / current_folder
        requested_destination = destination_dir / item["path"].name
        destination = requested_destination
        materialization = "dry_run"

        if not dry_run:
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination, existing_same_source = _collision_safe_destination(
                requested_destination, item["path"]
            )
            if existing_same_source:
                materialization = "existing_same_source"
            else:
                materialization = _materialize(item["path"], destination, selected_mode)
            materialization_modes[materialization] += 1
            managed_files.append({
                "path": _managed_relative_path(output, destination),
                "mode": materialization,
            })

        rows.append({
            "filename": item["path"].name,
            "output_filename": destination.name,
            "taken_at": item["taken_at"].isoformat(sep=" "),
            "product_group": current_folder,
            "category": item["category"],
            "view": item["view"],
            "brand": item["brand"],
            "model": item["model"],
            "catalog_match": item["catalog_match"],
            "confidence": item["confidence"],
            "status": "needs_review" if review else "classified",
            "reason": item["reason"],
        })

    if not dry_run:
        report_temp = report_path.with_name(f"{report_path.name}.tmp")
        with report_temp.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(rows[0]) if rows else ["filename"],
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(report_temp, report_path)

        _write_json_atomic(
            output / MANIFEST_NAME,
            {
                "schema": 2,
                "output_mode": selected_mode,
                "files": managed_files,
                "materialization": dict(materialization_modes),
            },
        )
        if hasattr(module, "append_log"):
            summary = "; ".join(
                f"{name}={count}" for name, count in sorted(materialization_modes.items())
            ) or "no_files=0"
            module.append_log(
                output,
                "OUTPUT_BUILT",
                f"mode={selected_mode}; {summary}",
            )

    print(f"Grouped {len(rows)} photos into {product_number} tentative products")
    if not dry_run:
        print(f"Report: {report_path}")


def apply_hardening(module: Any) -> None:
    """Patch the legacy-compatible engine in-place before its public export."""

    module.CATEGORIES = set(RETAIL_CATEGORIES)
    if module.Image is not None:
        module.Image.MAX_IMAGE_PIXELS = MAX_TRUSTED_IMAGE_PIXELS

    def compressed_image_bytes(path: Path) -> bytes:
        return _compressed_image_bytes(module, path)

    def prompt_for(photos: list[Any], catalog: str) -> str:
        return _prompt_for(module, photos, catalog)

    def build_outputs(
        items: list[dict[str, Any]], output: Path, confidence: float, dry_run: bool
    ) -> None:
        _build_outputs(module, items, output, confidence, dry_run)

    module.compressed_image_bytes = compressed_image_bytes
    module.prompt_for = prompt_for
    module.build_outputs = build_outputs
