"""Ground-truth dataset preparation and conservative hybrid-threshold calibration.

This module never enables production routing. It turns labeled product groups and
Hybrid Shadow evidence into a reproducible recommendation that can later be used
to decide whether routing is safe enough to promote.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
GROUND_TRUTH_FIELDS = (
    "filename", "category", "view", "brand", "model", "product_group"
)
DEFAULT_MIN_PRECISION = 0.98
DEFAULT_MIN_BOUNDARIES = 30
DEFAULT_MIN_DECISIONS = 5


@dataclass(frozen=True)
class LabeledBoundary:
    previous_filename: str
    filename: str
    similarity: float
    same_product: bool


def source_filenames(source: Path) -> list[str]:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Source folder does not exist: {source}")
    return sorted(
        (path.name for path in source.iterdir()
         if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=str.casefold,
    )


def write_ground_truth_template(source: Path, output: Path) -> dict[str, Any]:
    names = source_filenames(source)
    if not names:
        raise ValueError("No JPG/JPEG product photos were found in the source folder")
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GROUND_TRUTH_FIELDS))
        writer.writeheader()
        for name in names:
            writer.writerow({field: name if field == "filename" else "" for field in GROUND_TRUTH_FIELDS})
    return {"path": str(output), "photos": len(names), "fields": list(GROUND_TRUTH_FIELDS)}


def _read_csv(path: Path) -> list[dict[str, str]]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except csv.Error as exc:
        raise ValueError(f"Could not read CSV {path}: {exc}") from exc


def ground_truth_groups(path: Path) -> dict[str, str]:
    groups: dict[str, str] = {}
    seen: set[str] = set()
    for row in _read_csv(path):
        name = str(row.get("filename", "")).strip()
        if not name:
            continue
        if name in seen:
            raise ValueError(f"Duplicate filename in ground truth: {name}")
        seen.add(name)
        group = str(row.get("product_group", "")).strip()
        if group:
            groups[name] = group
    return groups


def validate_ground_truth(source: Path, ground_truth: Path) -> dict[str, Any]:
    names = source_filenames(source)
    source_set = set(names)
    rows = _read_csv(ground_truth)
    seen: set[str] = set()
    duplicates: list[str] = []
    unknown: list[str] = []
    labeled_groups: dict[str, str] = {}
    populated = 0
    for row in rows:
        name = str(row.get("filename", "")).strip()
        if not name:
            continue
        if name in seen:
            duplicates.append(name)
            continue
        seen.add(name)
        if name not in source_set:
            unknown.append(name)
        group = str(row.get("product_group", "")).strip()
        if group:
            labeled_groups[name] = group
            populated += 1
    missing = [name for name in names if name not in seen]
    unique_groups = sorted(set(labeled_groups.values()))
    return {
        "source_photos": len(names),
        "csv_rows": len(rows),
        "filenames_present": len(seen),
        "product_group_labeled": populated,
        "product_group_coverage": populated / len(names) if names else 0.0,
        "unique_product_groups": len(unique_groups),
        "duplicate_filenames": sorted(set(duplicates)),
        "unknown_filenames": sorted(set(unknown)),
        "missing_filenames": missing,
        "valid_for_calibration": bool(names) and not duplicates and not unknown and not missing and populated == len(names),
    }


def _relation_from_row(row: dict[str, str], groups: dict[str, str]) -> bool | None:
    relation = str(row.get("ground_truth_relation", "")).strip().lower()
    if relation == "same":
        return True
    if relation == "different":
        return False
    previous = str(row.get("previous_filename", "")).strip()
    current = str(row.get("filename", "")).strip()
    if previous in groups and current in groups:
        return groups[previous] == groups[current]
    return None


def load_labeled_boundaries(shadow_csv: Path, ground_truth: Path | None = None) -> list[LabeledBoundary]:
    groups = ground_truth_groups(ground_truth) if ground_truth is not None else {}
    boundaries: list[LabeledBoundary] = []
    for row in _read_csv(shadow_csv):
        relation = _relation_from_row(row, groups)
        if relation is None:
            continue
        try:
            similarity = float(str(row.get("cosine_similarity", "")).strip())
        except ValueError:
            continue
        boundaries.append(
            LabeledBoundary(
                previous_filename=str(row.get("previous_filename", "")).strip(),
                filename=str(row.get("filename", "")).strip(),
                similarity=similarity,
                same_product=relation,
            )
        )
    return boundaries


def _same_candidates(boundaries: list[LabeledBoundary], minimum_precision: float, minimum_decisions: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for threshold in sorted({row.similarity for row in boundaries}):
        predicted = [row for row in boundaries if row.similarity >= threshold]
        if len(predicted) < minimum_decisions:
            continue
        correct = sum(row.same_product for row in predicted)
        precision = correct / len(predicted)
        if precision >= minimum_precision:
            result.append({"threshold": threshold, "decisions": len(predicted), "correct": correct, "precision": precision})
    return result


def _different_candidates(boundaries: list[LabeledBoundary], minimum_precision: float, minimum_decisions: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for threshold in sorted({row.similarity for row in boundaries}):
        predicted = [row for row in boundaries if row.similarity <= threshold]
        if len(predicted) < minimum_decisions:
            continue
        correct = sum(not row.same_product for row in predicted)
        precision = correct / len(predicted)
        if precision >= minimum_precision:
            result.append({"threshold": threshold, "decisions": len(predicted), "correct": correct, "precision": precision})
    return result


def calibrate_thresholds(
    boundaries: list[LabeledBoundary],
    *,
    minimum_precision: float = DEFAULT_MIN_PRECISION,
    minimum_boundaries: int = DEFAULT_MIN_BOUNDARIES,
    minimum_decisions: int = DEFAULT_MIN_DECISIONS,
) -> dict[str, Any]:
    if not 0.5 <= minimum_precision <= 1.0:
        raise ValueError("minimum_precision must be between 0.5 and 1.0")
    if minimum_boundaries < 1 or minimum_decisions < 1:
        raise ValueError("minimum_boundaries and minimum_decisions must be positive")
    if not boundaries:
        raise ValueError("No labeled adjacent boundaries are available for calibration")

    same_options = _same_candidates(boundaries, minimum_precision, minimum_decisions)
    different_options = _different_candidates(boundaries, minimum_precision, minimum_decisions)
    best: dict[str, Any] | None = None
    for same in same_options:
        for different in different_options:
            if float(different["threshold"]) >= float(same["threshold"]):
                continue
            confident = [
                row for row in boundaries
                if row.similarity >= float(same["threshold"])
                or row.similarity <= float(different["threshold"])
            ]
            correct = sum(
                (row.same_product if row.similarity >= float(same["threshold"])
                 else not row.same_product)
                for row in confident
            )
            candidate = {
                "same_threshold": float(same["threshold"]),
                "different_threshold": float(different["threshold"]),
                "same_precision": float(same["precision"]),
                "different_precision": float(different["precision"]),
                "same_decisions": int(same["decisions"]),
                "different_decisions": int(different["decisions"]),
                "confident_decisions": len(confident),
                "confident_accuracy": correct / len(confident) if confident else 0.0,
                "confident_coverage": len(confident) / len(boundaries),
                "ambiguous_boundaries": len(boundaries) - len(confident),
            }
            key = (
                candidate["confident_coverage"],
                min(candidate["same_precision"], candidate["different_precision"]),
                candidate["confident_accuracy"],
            )
            if best is None or key > best["_key"]:
                candidate["_key"] = key
                best = candidate

    same_truth = sum(row.same_product for row in boundaries)
    different_truth = len(boundaries) - same_truth
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "calibration_recommendation",
        "routing_enabled": False,
        "labeled_boundaries": len(boundaries),
        "same_boundaries": same_truth,
        "different_boundaries": different_truth,
        "minimum_precision": minimum_precision,
        "minimum_boundaries": minimum_boundaries,
        "minimum_decisions_per_side": minimum_decisions,
        "sample_size_gate_passed": len(boundaries) >= minimum_boundaries,
        "recommendation_available": best is not None,
        "promotion_ready": bool(best is not None and len(boundaries) >= minimum_boundaries),
        "note": (
            "This is a calibration recommendation, not a production guarantee. "
            "Production hybrid routing remains disabled until representative datasets "
            "and review evidence justify promotion."
        ),
    }
    if best is not None:
        best.pop("_key", None)
        result.update(best)
    else:
        result["reason"] = (
            "No non-overlapping same/different thresholds met the requested precision "
            "and minimum-decision constraints. Keep routing in Shadow Mode."
        )
    return result


def render_calibration_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Hybrid Threshold Calibration",
        "",
        "This report recommends conservative Shadow Mode thresholds. It does not enable production routing.",
        "",
        f"- Labeled adjacent boundaries: `{result.get('labeled_boundaries', 0)}`",
        f"- Same-product boundaries: `{result.get('same_boundaries', 0)}`",
        f"- Different-product boundaries: `{result.get('different_boundaries', 0)}`",
        f"- Required precision per decision side: `{float(result.get('minimum_precision', 0.0)):.2%}`",
        f"- Sample-size gate passed: `{bool(result.get('sample_size_gate_passed'))}`",
        f"- Promotion-ready recommendation: `{bool(result.get('promotion_ready'))}`",
    ]
    if result.get("recommendation_available"):
        lines += [
            "",
            "## Recommended thresholds",
            "",
            f"- Same-product threshold: `{float(result['same_threshold']):.6f}`",
            f"- Different-product threshold: `{float(result['different_threshold']):.6f}`",
            f"- Same-decision precision: `{float(result['same_precision']):.2%}`",
            f"- Different-decision precision: `{float(result['different_precision']):.2%}`",
            f"- Confident coverage: `{float(result['confident_coverage']):.2%}`",
            f"- Accuracy across confident decisions: `{float(result['confident_accuracy']):.2%}`",
            f"- Ambiguous boundaries kept for Vision AI: `{result['ambiguous_boundaries']}`",
        ]
    else:
        lines += ["", "## No recommendation", "", str(result.get("reason", "No safe threshold pair found."))]
    lines += ["", "## Safety", "", str(result.get("note", "")), ""]
    return "\n".join(lines)


def write_calibration_report(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "hybrid_threshold_calibration.json"
    md_path = output_dir / "HYBRID_THRESHOLD_CALIBRATION.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_calibration_markdown(result), encoding="utf-8")
    return json_path, md_path


def calibrate_from_files(
    shadow_csv: Path,
    *,
    ground_truth: Path | None = None,
    output_dir: Path | None = None,
    minimum_precision: float = DEFAULT_MIN_PRECISION,
    minimum_boundaries: int = DEFAULT_MIN_BOUNDARIES,
    minimum_decisions: int = DEFAULT_MIN_DECISIONS,
) -> tuple[dict[str, Any], Path, Path]:
    boundaries = load_labeled_boundaries(shadow_csv, ground_truth)
    result = calibrate_thresholds(
        boundaries,
        minimum_precision=minimum_precision,
        minimum_boundaries=minimum_boundaries,
        minimum_decisions=minimum_decisions,
    )
    destination = output_dir or shadow_csv.expanduser().resolve().parent
    json_path, md_path = write_calibration_report(result, destination)
    return result, json_path, md_path


def _print_help() -> None:
    print(
        "\nBenchmark dataset / hybrid calibration:\n"
        "  --prepare-ground-truth DIR       Create a label CSV for JPG/JPEG photos and exit\n"
        "  --ground-truth-out FILE          Output path for the generated label CSV\n"
        "  --calibrate-hybrid SHADOW.csv    Calibrate from Hybrid Shadow evidence and exit\n"
        "  --calibration-ground-truth FILE  Optional labeled CSV when shadow rows lack truth\n"
        "  --calibration-output DIR         Directory for JSON + Markdown calibration report\n"
        "  --calibration-min-precision N    Required precision per confident side (default 0.98)\n"
        "  --calibration-min-boundaries N   Minimum labeled adjacent boundaries (default 30)\n"
        "  --calibration-min-decisions N    Minimum confident decisions per side (default 5)"
    )


def apply_threshold_calibration(module: Any) -> None:
    """Add standalone dataset/calibration CLI actions without altering normal runs."""
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--prepare-ground-truth", type=Path)
        parser.add_argument("--ground-truth-out", type=Path)
        parser.add_argument("--calibrate-hybrid", type=Path)
        parser.add_argument("--calibration-ground-truth", type=Path)
        parser.add_argument("--calibration-output", type=Path)
        parser.add_argument("--calibration-min-precision", type=float, default=DEFAULT_MIN_PRECISION)
        parser.add_argument("--calibration-min-boundaries", type=int, default=DEFAULT_MIN_BOUNDARIES)
        parser.add_argument("--calibration-min-decisions", type=int, default=DEFAULT_MIN_DECISIONS)
        known, remaining = parser.parse_known_args(original[1:])
        action_count = int(known.prepare_ground_truth is not None) + int(known.calibrate_hybrid is not None)
        if action_count > 1:
            raise SystemExit("Choose either --prepare-ground-truth or --calibrate-hybrid, not both")
        if known.prepare_ground_truth is not None:
            target = known.ground_truth_out or known.prepare_ground_truth.expanduser().resolve().parent / "product_sorter_ground_truth.csv"
            try:
                summary = write_ground_truth_template(known.prepare_ground_truth, target)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Ground-truth template: {summary['path']}")
            print(f"Photos: {summary['photos']} · fill product_group before calibration")
            raise SystemExit(0)
        if known.calibrate_hybrid is not None:
            try:
                result, json_path, md_path = calibrate_from_files(
                    known.calibrate_hybrid,
                    ground_truth=known.calibration_ground_truth,
                    output_dir=known.calibration_output,
                    minimum_precision=known.calibration_min_precision,
                    minimum_boundaries=known.calibration_min_boundaries,
                    minimum_decisions=known.calibration_min_decisions,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Calibration JSON: {json_path}")
            print(f"Calibration report: {md_path}")
            if result.get("recommendation_available"):
                print(
                    "Recommended shadow thresholds: "
                    f"same >= {result['same_threshold']:.6f}, "
                    f"different <= {result['different_threshold']:.6f}"
                )
            else:
                print("No safe threshold pair met the requested calibration constraints.")
            raise SystemExit(0)

        calibration_flags = {
            "--ground-truth-out", "--calibration-ground-truth", "--calibration-output",
            "--calibration-min-precision", "--calibration-min-boundaries", "--calibration-min-decisions",
        }
        if any(flag in original for flag in calibration_flags):
            raise SystemExit("Calibration options require --prepare-ground-truth or --calibrate-hybrid")
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
