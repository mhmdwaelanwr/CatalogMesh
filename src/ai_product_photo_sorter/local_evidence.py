"""Local OCR + barcode evidence for catalog/SKU workflows.

This module is evidence-only. It scans product photos locally and records text,
barcode, and candidate catalog identifiers without changing product grouping,
matching catalog rows, or publishing anything.

The heavy backends are optional and imported lazily:
- RapidOCR + ONNX Runtime for offline OCR
- ZXing-C++ for EAN/UPC/Code128/QR/DataMatrix and related barcode formats
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:sku|model|mpn|item|part|code)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9._/\-]{2,})\b"
)
GENERIC_IDENTIFIER_PATTERN = re.compile(r"\b[A-Z0-9][A-Z0-9._/\-]{4,}\b", re.I)

OCRReader = Callable[[Path], list[dict[str, Any]]]
BarcodeReader = Callable[[Path], list[dict[str, str]]]


def install_hint() -> str:
    return 'python -m pip install "ai-product-photo-sorter[local-evidence]"'


def backend_status() -> dict[str, bool]:
    def available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    return {
        "rapidocr": available("rapidocr"),
        "onnxruntime": available("onnxruntime"),
        "zxingcpp": available("zxingcpp"),
    }


def source_photos(source: Path) -> list[Path]:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Source folder does not exist: {source}")
    photos = sorted(
        (
            path
            for path in source.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )
    if not photos:
        raise ValueError("No JPG/JPEG product photos were found in the source folder")
    return photos


def build_ocr_reader(*, minimum_score: float = 0.50) -> OCRReader:
    status = backend_status()
    if not (status["rapidocr"] and status["onnxruntime"]):
        raise RuntimeError(
            "Local OCR requires RapidOCR and ONNX Runtime. "
            f"Install the optional runtime with: {install_hint()}"
        )
    from rapidocr import RapidOCR

    engine = RapidOCR(params={"Global.text_score": float(minimum_score)})

    def read(path: Path) -> list[dict[str, Any]]:
        result = engine(str(path))
        texts = getattr(result, "txts", None) or ()
        scores = getattr(result, "scores", None) or ()
        rows: list[dict[str, Any]] = []
        for text, score in zip(texts, scores):
            value = str(text).strip()
            if not value:
                continue
            rows.append({"text": value, "score": float(score)})
        return rows

    return read


def build_barcode_reader() -> BarcodeReader:
    if not backend_status()["zxingcpp"]:
        raise RuntimeError(
            "Local barcode scanning requires ZXing-C++. "
            f"Install the optional runtime with: {install_hint()}"
        )
    import numpy as np
    import zxingcpp

    def read(path: Path) -> list[dict[str, str]]:
        with Image.open(path) as image:
            image = image.convert("RGB")
            pixels = np.asarray(image)
        results = zxingcpp.read_barcodes(pixels)
        rows: list[dict[str, str]] = []
        for result in results:
            text = str(getattr(result, "text", "")).strip()
            if not text:
                continue
            rows.append(
                {
                    "text": text,
                    "format": str(getattr(result, "format", "unknown")),
                    "content_type": str(getattr(result, "content_type", "unknown")),
                }
            )
        return rows

    return read


def identifier_candidates(
    ocr_rows: list[dict[str, Any]], barcode_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(value: str, source: str) -> None:
        value = value.strip().strip(".,;()[]{}")
        key = value.casefold()
        if len(value) < 3 or key in seen:
            return
        seen.add(key)
        candidates.append({"value": value, "source": source})

    for row in barcode_rows:
        add(str(row.get("text", "")), "barcode")

    for row in ocr_rows:
        text = str(row.get("text", ""))
        for match in TOKEN_PATTERN.finditer(text):
            add(match.group(1), "ocr_labeled")
        for match in GENERIC_IDENTIFIER_PATTERN.finditer(text):
            value = match.group(0)
            if any(char.isdigit() for char in value) and any(char.isalpha() for char in value):
                add(value, "ocr_token")
    return candidates


def scan_source(
    source: Path,
    *,
    output_dir: Path,
    use_ocr: bool = True,
    use_barcode: bool = True,
    minimum_ocr_score: float = 0.50,
    ocr_reader: OCRReader | None = None,
    barcode_reader: BarcodeReader | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    if not use_ocr and not use_barcode:
        raise ValueError("Enable at least one local evidence backend: OCR or barcode")
    if not 0.0 <= minimum_ocr_score <= 1.0:
        raise ValueError("minimum_ocr_score must be between 0 and 1")

    photos = source_photos(source)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if use_ocr and ocr_reader is None:
        ocr_reader = build_ocr_reader(minimum_score=minimum_ocr_score)
    if use_barcode and barcode_reader is None:
        barcode_reader = build_barcode_reader()

    started = time.perf_counter()
    evidence_rows: list[dict[str, Any]] = []
    ocr_photo_hits = 0
    barcode_photo_hits = 0
    candidate_photo_hits = 0
    errors = 0
    total_ocr_regions = 0
    total_barcodes = 0

    for path in photos:
        ocr_rows: list[dict[str, Any]] = []
        barcode_rows: list[dict[str, str]] = []
        row_errors: list[str] = []
        if use_ocr and ocr_reader is not None:
            try:
                ocr_rows = ocr_reader(path)
            except Exception as exc:  # backend/image failures become evidence, not run aborts
                row_errors.append(f"ocr: {type(exc).__name__}: {exc}")
        if use_barcode and barcode_reader is not None:
            try:
                barcode_rows = barcode_reader(path)
            except Exception as exc:
                row_errors.append(f"barcode: {type(exc).__name__}: {exc}")

        candidates = identifier_candidates(ocr_rows, barcode_rows)
        ocr_photo_hits += int(bool(ocr_rows))
        barcode_photo_hits += int(bool(barcode_rows))
        candidate_photo_hits += int(bool(candidates))
        errors += int(bool(row_errors))
        total_ocr_regions += len(ocr_rows)
        total_barcodes += len(barcode_rows)

        evidence_rows.append(
            {
                "filename": path.name,
                "ocr": ocr_rows,
                "barcodes": barcode_rows,
                "identifier_candidates": candidates,
                "errors": row_errors,
            }
        )

    elapsed = max(0.0, time.perf_counter() - started)
    photo_count = len(photos)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "mode": "local_evidence",
        "production_matching_enabled": False,
        "production_routing_enabled": False,
        "source": str(source.expanduser().resolve()),
        "photos": photo_count,
        "elapsed_seconds": elapsed,
        "photos_per_second": photo_count / elapsed if elapsed else None,
        "ocr_enabled": use_ocr,
        "barcode_enabled": use_barcode,
        "minimum_ocr_score": minimum_ocr_score,
        "ocr_photo_hits": ocr_photo_hits,
        "ocr_photo_coverage": ocr_photo_hits / photo_count,
        "barcode_photo_hits": barcode_photo_hits,
        "barcode_photo_coverage": barcode_photo_hits / photo_count,
        "candidate_photo_hits": candidate_photo_hits,
        "candidate_photo_coverage": candidate_photo_hits / photo_count,
        "ocr_regions": total_ocr_regions,
        "barcodes": total_barcodes,
        "photos_with_backend_errors": errors,
        "backend_status": backend_status(),
        "note": (
            "Evidence only. OCR/barcode values are candidates for later SKU/catalog matching; "
            "this scan does not change product groups, match a catalog row, or publish data."
        ),
    }

    json_path = output_dir / "local_catalog_evidence.json"
    csv_path = output_dir / "local_catalog_evidence.csv"
    json_path.write_text(
        json.dumps({"summary": summary, "photos": evidence_rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "filename",
                "ocr_text",
                "ocr_max_score",
                "barcode_text",
                "barcode_formats",
                "identifier_candidates",
                "errors",
            ],
        )
        writer.writeheader()
        for row in evidence_rows:
            ocr_rows = row["ocr"]
            barcode_rows = row["barcodes"]
            candidate_rows = row["identifier_candidates"]
            writer.writerow(
                {
                    "filename": row["filename"],
                    "ocr_text": " | ".join(str(item["text"]) for item in ocr_rows),
                    "ocr_max_score": (
                        f"{max(float(item['score']) for item in ocr_rows):.6f}" if ocr_rows else ""
                    ),
                    "barcode_text": " | ".join(str(item["text"]) for item in barcode_rows),
                    "barcode_formats": " | ".join(str(item["format"]) for item in barcode_rows),
                    "identifier_candidates": " | ".join(
                        f"{item['value']} [{item['source']}]" for item in candidate_rows
                    ),
                    "errors": " | ".join(row["errors"]),
                }
            )
    return summary, json_path, csv_path


def _print_help() -> None:
    print(
        "\nLocal OCR + barcode evidence:\n"
        "  --local-evidence DIR             Scan a JPG/JPEG product folder locally and exit\n"
        "  --local-evidence-output DIR      Output directory for JSON + CSV evidence\n"
        "  --local-evidence-no-ocr          Disable OCR and scan barcodes only\n"
        "  --local-evidence-no-barcode      Disable barcodes and run OCR only\n"
        "  --local-evidence-ocr-score N     Minimum RapidOCR text score (default 0.50)"
    )


def apply_local_evidence(module: Any) -> None:
    """Add standalone local-evidence CLI actions without altering normal runs."""

    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--local-evidence", type=Path)
        parser.add_argument("--local-evidence-output", type=Path)
        parser.add_argument("--local-evidence-no-ocr", action="store_true")
        parser.add_argument("--local-evidence-no-barcode", action="store_true")
        parser.add_argument("--local-evidence-ocr-score", type=float, default=0.50)
        known, remaining = parser.parse_known_args(original[1:])

        if known.local_evidence is not None:
            destination = known.local_evidence_output or (
                known.local_evidence.expanduser().resolve().parent / "product_sorter_local_evidence"
            )
            try:
                summary, json_path, csv_path = scan_source(
                    known.local_evidence,
                    output_dir=destination,
                    use_ocr=not known.local_evidence_no_ocr,
                    use_barcode=not known.local_evidence_no_barcode,
                    minimum_ocr_score=known.local_evidence_ocr_score,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Local evidence JSON: {json_path}")
            print(f"Local evidence CSV: {csv_path}")
            print(
                f"Photos: {summary['photos']} · OCR hits: {summary['ocr_photo_hits']} · "
                f"barcode hits: {summary['barcode_photo_hits']} · "
                f"candidate hits: {summary['candidate_photo_hits']}"
            )
            print("Evidence only: production catalog matching remains disabled.")
            raise SystemExit(0)

        evidence_flags = {
            "--local-evidence-output",
            "--local-evidence-no-ocr",
            "--local-evidence-no-barcode",
            "--local-evidence-ocr-score",
        }
        if any(flag in original for flag in evidence_flags):
            raise SystemExit("Local evidence options require --local-evidence")
        try:
            sys.argv = [original[0], *remaining]
            return base_parse_args(env_file)
        except SystemExit as exc:
            if exc.code == 0 and any(flag in original for flag in ("-h", "--help")):
                _print_help()
            raise
        finally:
            sys.argv = original

    module.parse_args = parse_args
