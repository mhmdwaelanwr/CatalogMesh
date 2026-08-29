#!/usr/bin/env python3
"""Generate deterministic catalog/evidence inputs for SKU matching CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import openpyxl


CATALOG_ROWS = (
    ("SKU-M100", "6221111000017", "MockLab", "M100", "mouse", "MockLab M100 Mouse", 399),
    ("SKU-M110R", "6221111000024", "MockLab", "M110-R", "mouse", "MockLab M110-R Mouse", 449),
    ("SKU-K200", "6221111000031", "MockLab", "K200", "keyboard", "MockLab K200 Keyboard", 599),
    ("DISTRACTOR", "6221111000994", "Other", "Z900", "mouse", "Generic Mouse", 199),
)

EXPECTED = {
    "Product_0001_MockLab_M100": "MockCatalog!R2",
    "Product_0002_MockLab_M110": "MockCatalog!R3",
    "Product_0003_MockLab_K200": "MockCatalog!R4",
    "Product_0003B_MockLab_K200_Detail": "MockCatalog!R4",
}

PHOTO_IDENTIFIERS = {
    "P01": ("SKU-M100", "M100", "6221111000017"),
    "P02": ("SKU-M110R", "M110-R", "6221111000024"),
    "P03": ("SKU-K200", "K200", "6221111000031"),
}


def generate(review_output: Path) -> dict[str, object]:
    review_output = review_output.expanduser().resolve()
    approved = review_output / "approved_product_groups.csv"
    if not approved.is_file():
        raise ValueError(f"Approved Review Center export does not exist: {approved}")

    catalog = review_output / "mock_catalog.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "MockCatalog"
    sheet.append(["SKU", "Barcode", "Brand", "Model", "Category", "Name", "Price"])
    for row in CATALOG_ROWS:
        sheet.append(row)
    workbook.save(catalog)
    workbook.close()

    evidence_rows: list[dict[str, object]] = []
    for photo in sorted(review_output.rglob("*.jpg")):
        filename = photo.name
        prefix = filename[:3]
        sku, model, barcode = PHOTO_IDENTIFIERS[prefix]
        evidence_rows.append(
            {
                "filename": filename,
                "ocr": [
                    {"text": f"SKU: {sku}", "score": 0.99},
                    {"text": f"MODEL: {model}", "score": 0.98},
                ],
                "barcodes": [
                    {"text": barcode, "format": "EAN13", "content_type": "Text"}
                ],
                "identifier_candidates": [
                    {"value": barcode, "source": "barcode"},
                    {"value": sku, "source": "ocr_labeled"},
                    {"value": model, "source": "ocr_labeled"},
                ],
                "errors": [],
            }
        )

    evidence = review_output / "mock_local_catalog_evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "summary": {
                    "schema_version": 1,
                    "mode": "local_evidence",
                    "dataset_type": "synthetic_mock_sku",
                    "production_matching_enabled": False,
                    "production_routing_enabled": False,
                    "photos": len(evidence_rows),
                },
                "photos": evidence_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "schema_version": 1,
        "dataset_type": "synthetic_mock_sku",
        "production_evidence": False,
        "approved_groups": str(approved),
        "catalog": str(catalog),
        "evidence": str(evidence),
        "expected_top_rows": EXPECTED,
        "expected_confirmations": len(EXPECTED),
    }
    fixture = review_output / "mock_sku_fixture.json"
    fixture.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-output", type=Path, required=True)
    args = parser.parse_args()
    summary = generate(args.review_output)
    print(
        f"Mock SKU fixture: {len(CATALOG_ROWS)} catalog rows · "
        f"{summary['expected_confirmations']} approved groups"
    )
    print("WARNING: synthetic SKU fixture is engineering evidence only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
