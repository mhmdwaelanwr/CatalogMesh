"""Report discovery and lightweight Markdown parsing for the desktop preview."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_MAX_PREVIEW_BYTES = 5 * 1024 * 1024
_TOP_LEVEL_REPORTS = (
    "SMART_REPORT.md",
    "classification_report.csv",
    "processing_status.csv",
    "api_usage.csv",
    "error_report.csv",
    "quality_score.txt",
    "category_registry.json",
    "run_history.log",
)
_BENCHMARK_REPORTS = (
    "BENCHMARK_REPORT.md",
    "benchmark.json",
    "processing_status.csv",
    "api_usage.csv",
)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
_ORDERED = re.compile(r"^\s*(\d+)\.\s+(.*)$")


def report_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".md": "Markdown",
        ".json": "JSON",
        ".csv": "CSV",
        ".log": "Log",
        ".txt": "Text",
    }.get(suffix, "Text")


def read_report_text(path: Path) -> str:
    size = path.stat().st_size
    if size > _MAX_PREVIEW_BYTES:
        raise ValueError(
            f"Report is too large for the in-app preview ({size / 1024 / 1024:.1f} MiB)."
        )
    return path.read_text(encoding="utf-8-sig", errors="replace")


def discover_reports(output: Path | str | None) -> list[Path]:
    """Discover known report artifacts without recursively scanning photo folders."""
    if not output:
        return []
    root = Path(output).expanduser()
    if not root.is_dir():
        return []

    found: list[Path] = []
    for name in _TOP_LEVEL_REPORTS:
        path = root / name
        if path.is_file():
            found.append(path)

    benchmark_root = root / "benchmarks"
    if benchmark_root.is_dir():
        try:
            runs = [path for path in benchmark_root.iterdir() if path.is_dir()]
        except OSError:
            runs = []
        for run in runs:
            for name in _BENCHMARK_REPORTS:
                path = run / name
                if path.is_file():
                    found.append(path)

    # When the selected output is itself an isolated benchmark run.
    for name in _BENCHMARK_REPORTS:
        path = root / name
        if path.is_file() and path not in found:
            found.append(path)

    unique: dict[str, Path] = {}
    for path in found:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path.absolute())
        unique[key] = path

    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(unique.values(), key=modified, reverse=True)


def markdown_blocks(text: str) -> list[dict[str, Any]]:
    """Parse the Markdown subset emitted by Product Sorter's own reports."""
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    code: list[str] = []
    in_code = False
    code_language = ""

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append({"kind": "code", "text": "\n".join(code), "language": code_language})
                code = []
                code_language = ""
                in_code = False
            else:
                in_code = True
                code_language = stripped[3:].strip()
            continue
        if in_code:
            code.append(raw)
            continue
        if not stripped:
            blocks.append({"kind": "blank", "text": ""})
            continue
        if stripped in {"---", "***", "___"}:
            blocks.append({"kind": "hr", "text": ""})
            continue
        if raw.lstrip().startswith("#"):
            leading = raw.lstrip()
            level = len(leading) - len(leading.lstrip("#"))
            if 1 <= level <= 6 and leading[level:level + 1] == " ":
                blocks.append({"kind": "heading", "level": level, "text": leading[level + 1:]})
                continue
        if stripped.startswith(">"):
            blocks.append({"kind": "quote", "text": stripped[1:].lstrip()})
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                blocks.append({"kind": "table_separator", "cells": cells})
            else:
                blocks.append({"kind": "table", "cells": cells})
            continue
        if stripped.startswith(("- ", "* ", "+ ")):
            blocks.append({"kind": "bullet", "text": stripped[2:].strip()})
            continue
        ordered = _ORDERED.match(raw)
        if ordered:
            blocks.append({"kind": "ordered", "number": ordered.group(1), "text": ordered.group(2)})
            continue
        blocks.append({"kind": "paragraph", "text": raw.strip()})

    if in_code:
        blocks.append({"kind": "code", "text": "\n".join(code), "language": code_language})
    return blocks
