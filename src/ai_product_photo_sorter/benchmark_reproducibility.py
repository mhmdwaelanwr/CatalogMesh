"""Reproducibility metadata for Benchmark Center reports.

This extension keeps benchmark instrumentation separate from the compatibility-
preserved engine while making generated reports self-describing enough for fair
provider/model comparisons.
"""

from __future__ import annotations

import os
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any

from . import benchmark as benchmark_module

_LATENCY_RE = re.compile(r"latency_ms=([0-9]+(?:\.[0-9]+)?)")


def _network_latency_facts(output: Path) -> dict[str, Any]:
    """Summarize the connectivity probes already recorded by the real engine."""
    path = output / "run_history.log"
    samples: list[float] = []
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if "INTERNET_CHECK" not in line:
                    continue
                match = _LATENCY_RE.search(line)
                if match:
                    samples.append(float(match.group(1)))
        except (OSError, ValueError):
            samples = []
    if not samples:
        return {
            "sample_count": 0,
            "average": None,
            "median": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "sample_count": len(samples),
        "average": statistics.fmean(samples),
        "median": statistics.median(samples),
        "minimum": min(samples),
        "maximum": max(samples),
    }


def _code_revision() -> str | None:
    """Return a commit SHA when the running build can identify one safely."""
    for name in ("PRODUCT_SORTER_COMMIT", "GITHUB_SHA"):
        value = os.getenv(name, "").strip()
        if value:
            return value

    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _provider_priority() -> list[str]:
    raw = os.getenv("AI_PROVIDERS", os.getenv("AI_PROVIDER", "gemini"))
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _validate_keys_enabled(args: Any) -> bool:
    configured = os.getenv("VALIDATE_KEYS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return bool(getattr(args, "validate_keys", False) or configured)


def _configuration_snapshot(module: Any, args: Any) -> dict[str, Any]:
    return {
        "product_sorter_version": str(getattr(module, "VERSION", "unknown")),
        "code_revision": _code_revision(),
        "provider_priority": _provider_priority(),
        "requested_model": str(getattr(args, "model", "")),
        "batch_size": int(getattr(args, "batch_size", 0) or 0),
        "confidence": float(getattr(args, "confidence", 0.0) or 0.0),
        "max_retries": int(getattr(args, "max_retries", 0) or 0),
        "photo_limit": getattr(args, "limit", None),
        "ground_truth_enabled": bool(getattr(args, "ground_truth", None)),
        "key_validation_enabled": _validate_keys_enabled(args),
    }


def _fmt_ms(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.1f} ms"


def apply_benchmark_reproducibility(module: Any) -> None:
    """Add reproducibility/configuration facts to Benchmark Center reports."""
    base_parse_args = module.parse_args
    base_build_result = benchmark_module.build_result
    base_render_markdown = benchmark_module.render_markdown

    def parse_args(env_file: Path):
        args = base_parse_args(env_file)
        session = benchmark_module._ACTIVE
        if getattr(args, "benchmark", False) and session is not None:
            session.reproducibility = _configuration_snapshot(module, args)
        return args

    def build_result(session: Any) -> dict[str, Any]:
        result = base_build_result(session)
        result["benchmark_config"] = dict(
            getattr(session, "reproducibility", {}) or {}
        )
        result["network_latency_ms"] = _network_latency_facts(session.run_output)
        return result

    def render_markdown(result: dict[str, Any]) -> str:
        text = base_render_markdown(result)
        config = result.get("benchmark_config") or {}
        network = result.get("network_latency_ms") or {}
        providers = ", ".join(config.get("provider_priority") or []) or "unknown"
        revision = config.get("code_revision") or "unavailable"
        latency_samples = int(network.get("sample_count") or 0)
        if latency_samples:
            latency_text = (
                f"{_fmt_ms(network.get('average'))} avg · "
                f"{_fmt_ms(network.get('median'))} median · "
                f"{_fmt_ms(network.get('minimum'))}–{_fmt_ms(network.get('maximum'))} · "
                f"{latency_samples} probes"
            )
        else:
            latency_text = "Not measured"

        section = "\n".join(
            [
                "",
                "## Reproducibility",
                "",
                f"- Product Sorter version: `{config.get('product_sorter_version', 'unknown')}`",
                f"- Code revision: `{revision}`",
                f"- Provider priority: `{providers}`",
                f"- Requested model: `{config.get('requested_model', 'unknown')}`",
                f"- Batch size: `{config.get('batch_size', 'unknown')}`",
                f"- Confidence threshold: `{config.get('confidence', 'unknown')}`",
                f"- Maximum retries: `{config.get('max_retries', 'unknown')}`",
                f"- Photo limit: `{config.get('photo_limit') if config.get('photo_limit') is not None else 'all'}`",
                f"- Ground-truth scoring: `{'enabled' if config.get('ground_truth_enabled') else 'disabled'}`",
                f"- Key validation: `{'enabled' if config.get('key_validation_enabled') else 'disabled'}`",
                f"- Connectivity probe latency: {latency_text}",
                "",
            ]
        )
        marker = "\n## Provider timing\n"
        if marker in text:
            return text.replace(marker, section + "## Provider timing\n", 1)
        return text + section

    module.parse_args = parse_args
    benchmark_module.build_result = build_result
    benchmark_module.render_markdown = render_markdown
    module.render_benchmark_markdown = render_markdown
