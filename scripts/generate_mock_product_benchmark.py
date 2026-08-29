#!/usr/bin/env python3
"""Generate a deterministic mock product-shoot dataset and calibration evidence.

This utility validates Product Sorter's dataset/calibration workflow without
claiming real-world embedding quality. Similarity values are synthetic by design
and include deliberately ambiguous boundary cases.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ai_product_photo_sorter.threshold_calibration import calibrate_from_files

VIEWS = ("front", "back", "left", "right", "detail", "box")
PRODUCTS = (
    ("mouse", "MockLab", "M100", (62, 92, 150)),
    ("mouse", "MockLab", "M110", (67, 96, 154)),  # intentionally similar
    ("keyboard", "MockLab", "K200", (55, 63, 78)),
    ("keyboard", "MockLab", "K210", (58, 66, 82)),  # intentionally similar
    ("headset", "MockLab", "H300", (96, 64, 130)),
    ("gamepad", "MockLab", "G400", (45, 112, 103)),
    ("charger", "MockLab", "C500", (122, 92, 55)),
    ("usb_hub", "MockLab", "U600", (78, 84, 92)),
)


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _draw_product(draw: ImageDraw.ImageDraw, category: str, color: tuple[int, int, int], view_index: int) -> None:
    ox = (view_index % 3 - 1) * 14
    oy = (view_index // 3) * 8
    if category == "mouse":
        draw.ellipse((185 + ox, 135 + oy, 455 + ox, 495 + oy), fill=color, outline="white", width=5)
        draw.line((320 + ox, 150 + oy, 320 + ox, 315 + oy), fill="white", width=4)
    elif category == "keyboard":
        draw.rounded_rectangle((90 + ox, 210 + oy, 550 + ox, 410 + oy), radius=24, fill=color, outline="white", width=5)
        for row in range(4):
            for col in range(10):
                x = 115 + col * 42 + ox
                y = 235 + row * 38 + oy
                draw.rectangle((x, y, x + 28, y + 23), outline="white", width=2)
    elif category == "headset":
        draw.arc((145 + ox, 120 + oy, 495 + ox, 470 + oy), start=205, end=335, fill=color, width=38)
        draw.rounded_rectangle((135 + ox, 330 + oy, 235 + ox, 485 + oy), radius=30, fill=color, outline="white", width=4)
        draw.rounded_rectangle((405 + ox, 330 + oy, 505 + ox, 485 + oy), radius=30, fill=color, outline="white", width=4)
    elif category == "gamepad":
        draw.rounded_rectangle((125 + ox, 215 + oy, 515 + ox, 430 + oy), radius=90, fill=color, outline="white", width=5)
        draw.ellipse((210 + ox, 300 + oy, 260 + ox, 350 + oy), outline="white", width=4)
        draw.ellipse((380 + ox, 275 + oy, 420 + ox, 315 + oy), fill="white")
        draw.ellipse((430 + ox, 320 + oy, 470 + ox, 360 + oy), fill="white")
    elif category == "charger":
        draw.rounded_rectangle((205 + ox, 165 + oy, 435 + ox, 475 + oy), radius=30, fill=color, outline="white", width=5)
        draw.rectangle((250 + ox, 120 + oy, 280 + ox, 180 + oy), fill="white")
        draw.rectangle((360 + ox, 120 + oy, 390 + ox, 180 + oy), fill="white")
    else:
        draw.rounded_rectangle((120 + ox, 240 + oy, 520 + ox, 390 + oy), radius=24, fill=color, outline="white", width=5)
        for i in range(4):
            x = 175 + i * 85 + ox
            draw.rectangle((x, 300 + oy, x + 42, 326 + oy), outline="white", width=3)


def _render_photo(path: Path, *, category: str, brand: str, model: str, color: tuple[int, int, int], view: str, view_index: int) -> None:
    image = Image.new("RGB", (640, 640), (232, 235, 239))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 640, 90), fill=(24, 29, 38))
    draw.text((28, 24), "MOCK PRODUCT SHOOT", font=_font(28), fill="white")
    _draw_product(draw, category, color, view_index)
    draw.text((30, 540), f"{brand} {model}", font=_font(24), fill=(28, 34, 45))
    draw.text((30, 575), f"{category} · {view}", font=_font(18), fill=(72, 78, 90))
    image.save(path, "JPEG", quality=90)


def _similarity_for_boundary(index: int, same_product: bool) -> float:
    # Synthetic evidence intentionally contains hard cases near the overlap zone.
    same_scores = (0.97, 0.95, 0.94, 0.93, 0.91, 0.89, 0.96, 0.94, 0.92, 0.73, 0.95, 0.93, 0.61)
    different_scores = (0.24, 0.31, 0.39, 0.90, 0.34, 0.79, 0.28)
    scores = same_scores if same_product else different_scores
    return scores[index % len(scores)]


def generate(root: Path) -> dict[str, object]:
    root = root.resolve()
    photos_dir = root / "photos"
    report_dir = root / "calibration"
    photos_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for product_index, (category, brand, model, color) in enumerate(PRODUCTS, 1):
        product_group = f"MOCK-{product_index:03d}"
        for view_index, view in enumerate(VIEWS, 1):
            filename = f"P{product_index:02d}_V{view_index:02d}_{view}.jpg"
            _render_photo(
                photos_dir / filename,
                category=category,
                brand=brand,
                model=model,
                color=color,
                view=view,
                view_index=view_index - 1,
            )
            rows.append({
                "filename": filename,
                "category": category,
                "view": view,
                "brand": brand,
                "model": model,
                "product_group": product_group,
            })

    ground_truth = root / "ground_truth.csv"
    with ground_truth.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "category", "view", "brand", "model", "product_group"])
        writer.writeheader()
        writer.writerows(rows)

    shadow_csv = root / "hybrid_embedding_shadow.csv"
    shadow_rows: list[dict[str, str]] = []
    same_counter = 0
    different_counter = 0
    for previous, current in zip(rows, rows[1:]):
        same_product = previous["product_group"] == current["product_group"]
        counter = same_counter if same_product else different_counter
        similarity = _similarity_for_boundary(counter, same_product)
        if same_product:
            same_counter += 1
        else:
            different_counter += 1
        shadow_rows.append({
            "previous_filename": previous["filename"],
            "filename": current["filename"],
            "cosine_similarity": f"{similarity:.8f}",
            "embedding_decision": "mock_unrouted",
            "sorter_relation": "unavailable",
            "agrees_with_sorter": "",
            "ground_truth_relation": "same" if same_product else "different",
            "agrees_with_ground_truth": "",
        })

    with shadow_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(shadow_rows[0]))
        writer.writeheader()
        writer.writerows(shadow_rows)

    calibration, json_path, markdown_path = calibrate_from_files(
        shadow_csv,
        ground_truth=ground_truth,
        output_dir=report_dir,
    )
    summary = {
        "schema_version": 1,
        "dataset_type": "synthetic_mock",
        "production_evidence": False,
        "photos": len(rows),
        "products": len(PRODUCTS),
        "adjacent_boundaries": len(shadow_rows),
        "ground_truth": str(ground_truth),
        "shadow_csv": str(shadow_csv),
        "calibration_json": str(json_path),
        "calibration_markdown": str(markdown_path),
        "calibration": calibration,
        "warning": "Mock similarities validate workflow behavior only. Do not use these thresholds for production routing.",
    }
    (root / "mock_benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic mock Product Sorter benchmark evidence")
    parser.add_argument("--output", type=Path, default=Path("mock-benchmark-output"))
    args = parser.parse_args()
    summary = generate(args.output)
    print(f"Mock photos: {summary['photos']} across {summary['products']} products")
    calibration = summary["calibration"]
    print(
        "Calibration: "
        f"coverage={float(calibration.get('confident_coverage', 0.0)):.2%} "
        f"accuracy={float(calibration.get('confident_accuracy', 0.0)):.2%} "
        f"promotion_ready={calibration.get('promotion_ready')}"
    )
    print("WARNING: mock evidence is not valid for production threshold promotion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
