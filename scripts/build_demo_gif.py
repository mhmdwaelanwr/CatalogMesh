#!/usr/bin/env python3
"""Build the README demo GIF from the repository's real application screenshots."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "screenshots" / "actual"
OUTPUT = ROOT / "docs" / "demo.gif"

FRAMES = [
    "light-operation-setup.jpg",
    "light-gemini-keys.jpg",
    "light-results-completed.jpg",
    "light-output-browser.jpg",
    "dark-operation-setup.jpg",
]

MAX_WIDTH = 900
DURATION_MS = 1500


def prepare(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image = image.convert("RGB")
        if image.width > MAX_WIDTH:
            height = round(image.height * MAX_WIDTH / image.width)
            image = image.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)
        # A shared adaptive palette keeps the animation compact while preserving UI text.
        return image.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)


def main() -> None:
    missing = [name for name in FRAMES if not (SCREENSHOTS / name).is_file()]
    if missing:
        raise SystemExit(f"Missing demo screenshots: {', '.join(missing)}")

    frames = [prepare(SCREENSHOTS / name) for name in FRAMES]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Created {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
