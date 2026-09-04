from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


DEFAULT_PANELS = (
    "light-01-operation.png",
    "dark-04-review.png",
    "light-07-storage.png",
    "dark-08-automation.png",
)


def build_hero(source_dir: Path, output: Path) -> None:
    missing = [name for name in DEFAULT_PANELS if not (source_dir / name).is_file()]
    if missing:
        raise SystemExit(f"Missing canonical GUI screenshot(s): {', '.join(missing)}")

    tile_width = 800
    tile_height = 500
    gap = 16
    border = 18

    tiles: list[Image.Image] = []
    for name in DEFAULT_PANELS:
        with Image.open(source_dir / name) as image:
            rgb = image.convert("RGB")
            tiles.append(
                ImageOps.fit(
                    rgb,
                    (tile_width, tile_height),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
            )

    canvas_width = border * 2 + tile_width * 2 + gap
    canvas_height = border * 2 + tile_height * 2 + gap
    canvas = Image.new("RGB", (canvas_width, canvas_height), (11, 18, 32))

    positions = (
        (border, border),
        (border + tile_width + gap, border),
        (border, border + tile_height + gap),
        (border + tile_width + gap, border + tile_height + gap),
    )
    for tile, position in zip(tiles, positions, strict=True):
        canvas.paste(tile, position)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, compress_level=9)
    print(f"Generated README hero: {output} ({canvas_width}x{canvas_height})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the CatalogMesh README hero from canonical CI GUI screenshots."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("docs/screenshots/ci/windows"),
        help="Directory containing the canonical packaged-Windows screenshots.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/screenshots/ci/windows/readme-hero.png"),
        help="Output PNG path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_hero(args.source_dir, args.output)


if __name__ == "__main__":
    main()
