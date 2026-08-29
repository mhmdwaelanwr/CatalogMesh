#!/usr/bin/env python3
"""Generate a deterministic Product Sorter output tree for Review Center CI."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PRODUCTS = (
    ("Product_0001_MockLab_M100", "mouse", "M100", "classified"),
    ("Product_0002_MockLab_M110", "mouse", "M110", "needs_review"),
    ("Product_0003_MockLab_K200", "keyboard", "K200", "classified"),
)
VIEWS = ("front", "back", "side", "detail")


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _render(path: Path, *, group: str, model: str, view: str, index: int) -> None:
    image = Image.new("RGB", (720, 520), (238, 240, 244))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 720, 86), fill=(27, 32, 42))
    draw.text((28, 23), "MOCK REVIEW FIXTURE", fill="white", font=_font(28))
    draw.rounded_rectangle(
        (125 + index * 8, 135, 595 - index * 6, 365),
        radius=36,
        fill=(75 + index * 8, 95 + index * 5, 135 + index * 4),
        outline="white",
        width=5,
    )
    draw.text((34, 405), f"{group}", fill=(30, 35, 44), font=_font(22))
    draw.text((34, 444), f"MODEL {model} · VIEW {view}", fill=(65, 72, 84), font=_font(20))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "JPEG", quality=92)


def generate(output: Path) -> dict[str, object]:
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    sequence = 0
    for product_index, (group, category, model, status) in enumerate(PRODUCTS, 1):
        parent = "Needs_Review" if status == "needs_review" else category
        for view_index, view in enumerate(VIEWS, 1):
            sequence += 1
            filename = f"P{product_index:02d}_{view_index:02d}_{view}.jpg"
            destination = output / parent / group / filename
            _render(destination, group=group, model=model, view=view, index=view_index)
            rows.append(
                {
                    "filename": filename,
                    "output_filename": filename,
                    "taken_at": f"2026-08-29 02:{sequence:02d}:00",
                    "product_group": group,
                    "category": category,
                    "view": view,
                    "brand": "MockLab",
                    "model": model,
                    "catalog_match": "",
                    "confidence": "0.62" if status == "needs_review" else "0.94",
                    "status": status,
                    "reason": "mock review fixture",
                }
            )

    report = output / "classification_report.csv"
    with report.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    plan = {
        "operations": [
            {
                "action": "set_group",
                "group": "Product_0002_MockLab_M110",
                "model": "M110-R",
                "notes": "Mock human correction",
            },
            {
                "action": "set_view",
                "filename": "P02_04_detail.jpg",
                "view": "packaging_detail",
            },
            {
                "action": "split",
                "group": "Product_0003_MockLab_K200",
                "filenames": ["P03_04_detail.jpg"],
                "new_group": "Product_0003B_MockLab_K200_Detail",
            },
            {"action": "approve", "group": "Product_0001_MockLab_M100"},
            {"action": "approve", "group": "Product_0002_MockLab_M110"},
            {"action": "approve", "group": "Product_0003_MockLab_K200"},
            {"action": "approve", "group": "Product_0003B_MockLab_K200_Detail"},
        ]
    }
    plan_path = output / "mock_review_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "schema_version": 1,
        "dataset_type": "synthetic_mock_review",
        "production_evidence": False,
        "photos": len(rows),
        "initial_groups": len(PRODUCTS),
        "expected_groups_after_plan": 4,
        "expected_audit_events": len(plan["operations"]),
        "report": str(report),
        "plan": str(plan_path),
    }
    (output / "mock_review_fixture.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = generate(args.output)
    print(
        f"Mock review fixture: {summary['photos']} photos across "
        f"{summary['initial_groups']} initial groups"
    )
    print("WARNING: synthetic review fixture is engineering evidence only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
