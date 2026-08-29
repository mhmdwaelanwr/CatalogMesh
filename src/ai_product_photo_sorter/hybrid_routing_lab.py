"""Hybrid routing simulation for measured Shadow evidence.

This module deliberately does not alter production inference. It replays measured
adjacent-boundary similarities through calibrated thresholds and estimates how
much boundary work could be handled locally while keeping ambiguous cases on the
Vision path. When ground-truth relations are available it also reports unsafe
local misroutes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from .threshold_calibration import ground_truth_groups

SIMULATION_MODE = "simulation"


def _read_csv(path: Path) -> list[dict[str, str]]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except csv.Error as exc:
        raise ValueError(f"Could not read CSV {path}: {exc}") from exc


def _load_calibration(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Calibration JSON does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read calibration JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Calibration JSON must contain an object")
    if not payload.get("recommendation_available"):
        raise ValueError("Calibration JSON does not contain a usable threshold recommendation")
    try:
        same = float(payload["same_threshold"])
        different = float(payload["different_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Calibration JSON is missing numeric same/different thresholds") from exc
    if not 0.0 <= different < same <= 1.0:
        raise ValueError("Calibration thresholds must satisfy 0 <= different < same <= 1")
    return {**payload, "same_threshold": same, "different_threshold": different}


def _truth_relation(row: dict[str, str], groups: dict[str, str]) -> bool | None:
    embedded = str(row.get("ground_truth_relation", "")).strip().lower()
    if embedded == "same":
        return True
    if embedded == "different":
        return False
    previous = str(row.get("previous_filename", "")).strip()
    current = str(row.get("filename", "")).strip()
    if previous in groups and current in groups:
        return groups[previous] == groups[current]
    return None


def simulate_routing(
    shadow_csv: Path,
    calibration_json: Path,
    *,
    ground_truth: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replay Shadow similarities through calibrated thresholds.

    The returned summary is evidence only. ``actual_provider_calls_skipped`` is
    always zero because this function never intercepts production provider calls.
    """

    rows = _read_csv(shadow_csv)
    if not rows:
        raise ValueError("Shadow CSV contains no adjacent-boundary rows")
    calibration = _load_calibration(calibration_json)
    groups = ground_truth_groups(ground_truth) if ground_truth is not None else {}
    same_threshold = float(calibration["same_threshold"])
    different_threshold = float(calibration["different_threshold"])

    evidence: list[dict[str, Any]] = []
    local_same = 0
    local_different = 0
    vision = 0
    comparable = 0
    correct = 0
    misroutes = 0

    for index, row in enumerate(rows, 1):
        previous = str(row.get("previous_filename", "")).strip()
        current = str(row.get("filename", "")).strip()
        if not previous or not current:
            raise ValueError(f"Shadow row {index} is missing previous_filename or filename")
        try:
            similarity = float(str(row.get("cosine_similarity", "")).strip())
        except ValueError as exc:
            raise ValueError(f"Shadow row {index} has an invalid cosine_similarity") from exc

        predicted_same: bool | None
        if similarity >= same_threshold:
            route = "local_same"
            predicted_same = True
            local_same += 1
        elif similarity <= different_threshold:
            route = "local_different"
            predicted_same = False
            local_different += 1
        else:
            route = "vision"
            predicted_same = None
            vision += 1

        truth = _truth_relation(row, groups)
        route_correct: bool | None = None
        if predicted_same is not None and truth is not None:
            comparable += 1
            route_correct = predicted_same == truth
            correct += int(route_correct)
            misroutes += int(not route_correct)

        evidence.append(
            {
                "previous_filename": previous,
                "filename": current,
                "cosine_similarity": similarity,
                "routing_decision": route,
                "predicted_relation": (
                    "same" if predicted_same is True else "different"
                    if predicted_same is False else "vision"
                ),
                "ground_truth_relation": (
                    "same" if truth is True else "different"
                    if truth is False else "unavailable"
                ),
                "local_route_correct": (
                    "true" if route_correct is True else "false"
                    if route_correct is False else ""
                ),
            }
        )

    total = len(evidence)
    local = local_same + local_different
    summary: dict[str, Any] = {
        "schema_version": 1,
        "mode": SIMULATION_MODE,
        "production_routing_enabled": False,
        "actual_provider_calls_skipped": 0,
        "same_threshold": same_threshold,
        "different_threshold": different_threshold,
        "adjacent_boundaries": total,
        "local_routed_boundaries": local,
        "local_same_boundaries": local_same,
        "local_different_boundaries": local_different,
        "vision_boundaries_remaining": vision,
        "local_routing_coverage": local / total if total else 0.0,
        "estimated_vision_boundary_work_reduction": local / total if total else 0.0,
        "ground_truth_local_boundaries": comparable,
        "local_routing_correct": correct,
        "local_routing_accuracy": correct / comparable if comparable else None,
        "unsafe_local_misroutes": misroutes,
        "safe_on_supplied_labels": bool(comparable and misroutes == 0),
        "note": (
            "Simulation only. No production provider call is skipped. Boundary-work "
            "reduction is an estimate and is not the same as provider API-call reduction, "
            "because production inference may batch multiple photos per request."
        ),
    }
    return summary, evidence


def render_markdown(summary: dict[str, Any]) -> str:
    accuracy = summary.get("local_routing_accuracy")
    accuracy_text = "n/a" if accuracy is None else f"{float(accuracy):.2%}"
    return "\n".join(
        [
            "# Hybrid Routing Lab",
            "",
            "Simulation evidence only. Production Hybrid Routing remains disabled.",
            "",
            f"- Same threshold: `{float(summary['same_threshold']):.6f}`",
            f"- Different threshold: `{float(summary['different_threshold']):.6f}`",
            f"- Adjacent boundaries: `{summary['adjacent_boundaries']}`",
            f"- Locally routed boundaries: `{summary['local_routed_boundaries']}`",
            f"- Vision boundaries remaining: `{summary['vision_boundaries_remaining']}`",
            f"- Estimated boundary-work reduction: `{float(summary['estimated_vision_boundary_work_reduction']):.2%}`",
            f"- Ground-truth local-routing accuracy: `{accuracy_text}`",
            f"- Unsafe local misroutes: `{summary['unsafe_local_misroutes']}`",
            f"- Actual provider calls skipped: `{summary['actual_provider_calls_skipped']}`",
            "",
            "## Safety",
            "",
            str(summary.get("note", "")),
            "",
        ]
    )


def write_simulation_report(
    summary: dict[str, Any],
    evidence: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "hybrid_routing_simulation.json"
    md_path = output_dir / "HYBRID_ROUTING_SIMULATION.md"
    csv_path = output_dir / "hybrid_routing_simulation.csv"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = [
            "previous_filename",
            "filename",
            "cosine_similarity",
            "routing_decision",
            "predicted_relation",
            "ground_truth_relation",
            "local_route_correct",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(evidence)
    return json_path, md_path, csv_path


def simulate_from_files(
    shadow_csv: Path,
    calibration_json: Path,
    *,
    ground_truth: Path | None = None,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], Path, Path, Path]:
    summary, evidence = simulate_routing(
        shadow_csv,
        calibration_json,
        ground_truth=ground_truth,
    )
    destination = output_dir or shadow_csv.expanduser().resolve().parent
    json_path, md_path, csv_path = write_simulation_report(summary, evidence, destination)
    return summary, json_path, md_path, csv_path


def _print_help() -> None:
    print(
        "\nHybrid Routing Lab (simulation only):\n"
        "  --simulate-hybrid-routing SHADOW.csv  Replay Shadow similarities through calibrated thresholds\n"
        "  --routing-calibration FILE            Calibration JSON containing recommended thresholds\n"
        "  --routing-ground-truth FILE           Optional product_group ground-truth CSV\n"
        "  --routing-output DIR                  Directory for simulation CSV/JSON/Markdown evidence"
    )


def apply_hybrid_routing_lab(module: Any) -> None:
    """Add standalone routing-simulation CLI actions without changing normal runs."""

    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--simulate-hybrid-routing", type=Path)
        parser.add_argument("--routing-calibration", type=Path)
        parser.add_argument("--routing-ground-truth", type=Path)
        parser.add_argument("--routing-output", type=Path)
        known, remaining = parser.parse_known_args(original[1:])

        if known.simulate_hybrid_routing is not None:
            if known.routing_calibration is None:
                raise SystemExit("--simulate-hybrid-routing requires --routing-calibration")
            try:
                summary, json_path, md_path, csv_path = simulate_from_files(
                    known.simulate_hybrid_routing,
                    known.routing_calibration,
                    ground_truth=known.routing_ground_truth,
                    output_dir=known.routing_output,
                )
            except (ValueError, OSError) as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Routing simulation JSON: {json_path}")
            print(f"Routing simulation report: {md_path}")
            print(f"Routing simulation CSV: {csv_path}")
            print(
                "Simulation: "
                f"local={summary['local_routed_boundaries']}/{summary['adjacent_boundaries']} "
                f"({float(summary['local_routing_coverage']):.2%}) · "
                f"vision={summary['vision_boundaries_remaining']} · "
                f"unsafe_misroutes={summary['unsafe_local_misroutes']}"
            )
            print("Production routing remains disabled; actual provider calls skipped: 0")
            raise SystemExit(0)

        routing_flags = {"--routing-calibration", "--routing-ground-truth", "--routing-output"}
        if any(flag in original for flag in routing_flags):
            raise SystemExit("Routing Lab options require --simulate-hybrid-routing")
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
