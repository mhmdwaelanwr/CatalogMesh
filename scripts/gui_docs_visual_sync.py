#!/usr/bin/env python3
"""Refresh tracked CatalogMesh GUI screenshots only for meaningful visual changes."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageStat

WORKSPACE_SLUGS = (
    "operation",
    "models",
    "results",
    "review",
    "sku-match",
    "exports",
    "storage",
    "automation",
    "reports",
    "benchmark",
    "environment",
    "about",
)
EXPECTED_SCREENSHOTS = tuple(
    f"{theme}-{index:02d}-{slug}.png"
    for theme in ("light", "dark")
    for index, slug in enumerate(WORKSPACE_SLUGS, start=1)
)
DEFAULT_THRESHOLD = 0.005


def image_delta(left: Image.Image, right: Image.Image) -> float:
    """Return normalized RGB RMS delta in the inclusive range 0..1."""
    first = left.convert("RGB")
    second = right.convert("RGB")
    if first.size != second.size:
        return 1.0
    diff = ImageChops.difference(first, second)
    rms = ImageStat.Stat(diff).rms
    return math.sqrt(sum(channel * channel for channel in rms) / len(rms)) / 255.0


def _candidate_names(directory: Path) -> set[str]:
    return {
        path.name
        for pattern in ("light-[0-9][0-9]-*.png", "dark-[0-9][0-9]-*.png")
        for path in directory.glob(pattern)
        if path.is_file()
    }


def sync_screenshots(
    candidate_dir: Path,
    tracked_dir: Path,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    expected_names: Iterable[str] = EXPECTED_SCREENSHOTS,
) -> dict[str, object]:
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")

    expected = tuple(expected_names)
    expected_set = set(expected)
    if len(expected_set) != len(expected):
        raise ValueError("expected screenshot names must be unique")

    candidate_dir = candidate_dir.resolve()
    tracked_dir = tracked_dir.resolve()
    if not candidate_dir.is_dir():
        raise FileNotFoundError(f"candidate directory not found: {candidate_dir}")
    tracked_dir.mkdir(parents=True, exist_ok=True)

    actual_candidates = _candidate_names(candidate_dir)
    if expected_set == set(EXPECTED_SCREENSHOTS):
        missing = expected_set - actual_candidates
        extras = actual_candidates - expected_set
        if missing or extras:
            details = []
            if missing:
                details.append("missing=" + ",".join(sorted(missing)))
            if extras:
                details.append("unexpected=" + ",".join(sorted(extras)))
            raise ValueError("canonical GUI screenshot set mismatch: " + "; ".join(details))

    changed: list[dict[str, object]] = []
    unchanged: list[dict[str, object]] = []
    for name in expected:
        candidate = candidate_dir / name
        tracked = tracked_dir / name
        if not candidate.is_file():
            raise FileNotFoundError(f"candidate screenshot not found: {candidate}")

        if not tracked.is_file():
            delta = 1.0
            reason = "missing-baseline"
        else:
            with Image.open(candidate) as candidate_image, Image.open(tracked) as tracked_image:
                delta = image_delta(candidate_image, tracked_image)
            reason = "visual-change" if delta > threshold else "below-threshold"

        record = {"file": name, "delta": round(delta, 6), "reason": reason}
        if delta > threshold:
            shutil.copyfile(candidate, tracked)
            changed.append(record)
        else:
            unchanged.append(record)

    return {
        "threshold": threshold,
        "expected_count": len(expected),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "changed": changed,
        "unchanged": unchanged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--tracked-dir", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    result = sync_screenshots(
        args.candidate_dir,
        args.tracked_dir,
        threshold=args.threshold,
    )
    text = json.dumps(result, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
