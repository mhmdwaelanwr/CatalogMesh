"""Measured local visual-embedding shadow analysis.

This module intentionally does *not* route or override production grouping yet.
It computes image embeddings before provider inference, records conservative
same/different/ambiguous adjacent-boundary candidates, and then compares those
candidates with the final sorter relation. That gives Benchmark Center evidence
for choosing thresholds before embeddings are allowed to skip Vision LLM work.

FastEmbed is optional and imported lazily. Product Sorter's normal cloud/Ollama
runtime stays lightweight unless the user explicitly installs and enables the
local-embeddings extra.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from . import benchmark as benchmark_module

DEFAULT_MODEL = "Qdrant/clip-ViT-B-32-vision"
DEFAULT_SAME_THRESHOLD = 0.90
DEFAULT_DIFFERENT_THRESHOLD = 0.50
DEFAULT_BATCH_SIZE = 16

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BoundaryCandidate:
    previous_filename: str
    filename: str
    similarity: float
    decision: str


@dataclass
class ShadowSession:
    model: str
    photo_count: int
    elapsed_seconds: float
    same_threshold: float
    different_threshold: float
    candidates: list[BoundaryCandidate]
    batch_size: int
    parallel: int | None


_LAST_SESSION: ShadowSession | None = None
_LAST_SUMMARY: dict[str, Any] = {}


def _enabled() -> bool:
    return os.getenv("HYBRID_EMBEDDINGS", "").strip().lower() in _TRUE


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parallel_value() -> int | None:
    raw = os.getenv("HYBRID_EMBEDDING_PARALLEL", "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _settings() -> dict[str, Any]:
    same = _float_env("HYBRID_SIMILARITY_SAME", DEFAULT_SAME_THRESHOLD)
    different = _float_env("HYBRID_SIMILARITY_DIFFERENT", DEFAULT_DIFFERENT_THRESHOLD)
    batch_size = _int_env("HYBRID_EMBEDDING_BATCH_SIZE", DEFAULT_BATCH_SIZE)
    if not (0.0 <= different < same <= 1.0):
        raise ValueError(
            "Hybrid thresholds must satisfy 0 <= different < same <= 1"
        )
    if not 1 <= batch_size <= 256:
        raise ValueError("HYBRID_EMBEDDING_BATCH_SIZE must be between 1 and 256")
    parallel = _parallel_value()
    if parallel is not None and parallel > 64:
        raise ValueError("HYBRID_EMBEDDING_PARALLEL must be blank or between 0 and 64")
    return {
        "model": os.getenv("HYBRID_EMBEDDING_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "same_threshold": same,
        "different_threshold": different,
        "batch_size": batch_size,
        "parallel": parallel,
        "cache_dir": os.getenv("HYBRID_EMBEDDING_CACHE_DIR", "").strip(),
    }


def fastembed_available() -> bool:
    try:
        return importlib.util.find_spec("fastembed") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def install_hint() -> str:
    return 'python -m pip install "ai-product-photo-sorter[local-embeddings]"'


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    count = 0
    for a, b in zip(left, right):
        a = float(a)
        b = float(b)
        dot += a * b
        left_norm += a * a
        right_norm += b * b
        count += 1
    if count == 0 or left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / math.sqrt(left_norm * right_norm)))


def _decision(similarity: float, *, same: float, different: float) -> str:
    if similarity >= same:
        return "same_candidate"
    if similarity <= different:
        return "different_candidate"
    return "ambiguous"


def _embed_paths(paths: list[Path], settings: dict[str, Any]) -> list[Any]:
    try:
        from fastembed import ImageEmbedding
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - preflight normally catches
        raise RuntimeError(
            "Hybrid local embeddings require the optional FastEmbed runtime. "
            f"Install it with: {install_hint()}"
        ) from exc

    kwargs: dict[str, Any] = {"model_name": settings["model"]}
    if settings["cache_dir"]:
        cache_dir = Path(settings["cache_dir"]).expanduser()
        cache_dir.mkdir(parents=True, exist_ok=True)
        kwargs["cache_dir"] = str(cache_dir)
    model = ImageEmbedding(**kwargs)
    return list(
        model.embed(
            [str(path) for path in paths],
            batch_size=settings["batch_size"],
            parallel=settings["parallel"],
        )
    )


def analyze_photos(photos: list[Any]) -> ShadowSession:
    settings = _settings()
    paths = [Path(photo.path) for photo in photos]
    started = time.perf_counter()
    embeddings = _embed_paths(paths, settings)
    elapsed = max(0.0, time.perf_counter() - started)
    if len(embeddings) != len(paths):
        raise RuntimeError(
            f"Hybrid embedding backend returned {len(embeddings)} vectors for {len(paths)} photos"
        )

    candidates: list[BoundaryCandidate] = []
    for index in range(1, len(paths)):
        similarity = _cosine(embeddings[index - 1], embeddings[index])
        candidates.append(
            BoundaryCandidate(
                previous_filename=paths[index - 1].name,
                filename=paths[index].name,
                similarity=similarity,
                decision=_decision(
                    similarity,
                    same=settings["same_threshold"],
                    different=settings["different_threshold"],
                ),
            )
        )
    return ShadowSession(
        model=settings["model"],
        photo_count=len(paths),
        elapsed_seconds=elapsed,
        same_threshold=settings["same_threshold"],
        different_threshold=settings["different_threshold"],
        candidates=candidates,
        batch_size=settings["batch_size"],
        parallel=settings["parallel"],
    )


def _write_shadow_evidence(
    items: list[dict[str, Any]],
    output: Path,
    session: ShadowSession,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    item_by_name = {
        Path(item["path"]).name: item
        for item in items
        if item.get("path") is not None
    }
    rows: list[dict[str, Any]] = []
    confident = 0
    agreement = 0
    same_candidates = 0
    different_candidates = 0
    ambiguous = 0

    for candidate in session.candidates:
        current = item_by_name.get(candidate.filename)
        sorter_same: bool | None = None
        agrees: bool | None = None
        if current is not None:
            sorter_same = bool(current.get("same_product_as_previous", False))
        if candidate.decision == "ambiguous":
            ambiguous += 1
        else:
            confident += 1
            predicted_same = candidate.decision == "same_candidate"
            if predicted_same:
                same_candidates += 1
            else:
                different_candidates += 1
            if sorter_same is not None:
                agrees = predicted_same == sorter_same
                agreement += int(agrees)
        rows.append(
            {
                "previous_filename": candidate.previous_filename,
                "filename": candidate.filename,
                "cosine_similarity": f"{candidate.similarity:.8f}",
                "embedding_decision": candidate.decision,
                "sorter_relation": (
                    "same" if sorter_same else "different"
                    if sorter_same is not None else "unavailable"
                ),
                "agrees_with_sorter": (
                    "true" if agrees is True else "false" if agrees is False else ""
                ),
            }
        )

    pair_count = len(session.candidates)
    comparable_confident = sum(
        1
        for row in rows
        if row["embedding_decision"] != "ambiguous" and row["sorter_relation"] != "unavailable"
    )
    summary = {
        "schema_version": 1,
        "mode": "shadow",
        "routing_enabled": False,
        "model": session.model,
        "photos": session.photo_count,
        "adjacent_pairs": pair_count,
        "embedding_seconds": session.elapsed_seconds,
        "photos_per_second": (
            session.photo_count / session.elapsed_seconds
            if session.elapsed_seconds > 0 else None
        ),
        "same_threshold": session.same_threshold,
        "different_threshold": session.different_threshold,
        "batch_size": session.batch_size,
        "parallel": session.parallel,
        "same_candidates": same_candidates,
        "different_candidates": different_candidates,
        "ambiguous_pairs": ambiguous,
        "confident_pairs": confident,
        "confident_coverage": confident / pair_count if pair_count else 0.0,
        "agreement_with_sorter": (
            agreement / comparable_confident if comparable_confident else None
        ),
        "comparable_confident_pairs": comparable_confident,
        "note": (
            "Shadow evidence only. Embedding decisions do not change production grouping. "
            "Agreement with sorter output is not ground-truth accuracy."
        ),
    }

    csv_path = output / "hybrid_embedding_shadow.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "previous_filename",
                "filename",
                "cosine_similarity",
                "embedding_decision",
                "sorter_relation",
                "agrees_with_sorter",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    (output / "hybrid_embedding_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _benchmark_markdown_section(summary: dict[str, Any]) -> str:
    if not summary:
        return ""
    throughput = summary.get("photos_per_second")
    agreement = summary.get("agreement_with_sorter")
    throughput_text = "n/a" if throughput is None else f"{float(throughput):.2f} photos/s"
    agreement_text = "n/a" if agreement is None else f"{float(agreement):.2%}"
    return "\n".join(
        [
            "",
            "## Hybrid visual-embedding shadow",
            "",
            f"- Model: `{summary.get('model', 'unknown')}`",
            "- Production routing: `disabled (measurement only)`",
            f"- Embedding time: `{float(summary.get('embedding_seconds', 0.0)):.3f}s`",
            f"- Embedding throughput: `{throughput_text}`",
            f"- Confident pair coverage: `{float(summary.get('confident_coverage', 0.0)):.2%}`",
            f"- Agreement with sorter boundaries: `{agreement_text}`",
            f"- Ambiguous pairs: `{summary.get('ambiguous_pairs', 0)}`",
            "- Interpretation: agreement is diagnostic evidence, not ground-truth accuracy.",
            "",
        ]
    )


def _install_cli_flags(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original_argv = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--hybrid-embeddings", action="store_true")
        parser.add_argument("--hybrid-embedding-model")
        parser.add_argument("--hybrid-same-threshold", type=float)
        parser.add_argument("--hybrid-different-threshold", type=float)
        parser.add_argument("--hybrid-embedding-batch-size", type=int)
        parser.add_argument("--hybrid-embedding-parallel", type=int)
        parser.add_argument("--hybrid-embedding-cache-dir")
        known, remaining = parser.parse_known_args(original_argv[1:])

        if known.hybrid_embeddings:
            os.environ["HYBRID_EMBEDDINGS"] = "true"
        mapping = {
            "HYBRID_EMBEDDING_MODEL": known.hybrid_embedding_model,
            "HYBRID_SIMILARITY_SAME": known.hybrid_same_threshold,
            "HYBRID_SIMILARITY_DIFFERENT": known.hybrid_different_threshold,
            "HYBRID_EMBEDDING_BATCH_SIZE": known.hybrid_embedding_batch_size,
            "HYBRID_EMBEDDING_PARALLEL": known.hybrid_embedding_parallel,
            "HYBRID_EMBEDDING_CACHE_DIR": known.hybrid_embedding_cache_dir,
        }
        for name, value in mapping.items():
            if value is not None:
                os.environ[name] = str(value)

        try:
            sys.argv = [original_argv[0], *remaining]
            args = base_parse_args(env_file)
        finally:
            sys.argv = original_argv
        args.hybrid_embeddings = _enabled()
        return args

    module.parse_args = parse_args


def apply_hybrid_embeddings(module: Any) -> None:
    """Install shadow-mode visual embeddings into the shared CLI/GUI engine."""
    global _LAST_SESSION, _LAST_SUMMARY
    base_ensure_requirements = module.ensure_requirements
    base_select_photo_sample = module.select_photo_sample
    base_build_outputs = module.build_outputs
    base_build_result = benchmark_module.build_result
    base_render_markdown = benchmark_module.render_markdown

    def ensure_requirements() -> bool:
        if not base_ensure_requirements():
            return False
        if _enabled() and not fastembed_available():
            print(
                "Hybrid local embeddings are enabled but FastEmbed is not installed.\n"
                f"Install the optional runtime with:\n  {install_hint()}",
                file=sys.stderr,
            )
            return False
        if _enabled():
            try:
                _settings()
            except ValueError as exc:
                print(f"Hybrid embedding configuration error: {exc}", file=sys.stderr)
                return False
        return True

    def select_photo_sample(photos, configured_limit):
        global _LAST_SESSION, _LAST_SUMMARY
        selected = base_select_photo_sample(photos, configured_limit)
        _LAST_SESSION = None
        _LAST_SUMMARY = {}
        module.HYBRID_EMBEDDING_SUMMARY = {}
        if not _enabled() or not selected:
            return selected
        print(
            f"Hybrid shadow: embedding {len(selected)} photos locally with "
            f"{_settings()['model']} (routing remains disabled)"
        )
        _LAST_SESSION = analyze_photos(selected)
        module.HYBRID_EMBEDDING_SESSION = _LAST_SESSION
        return selected

    def build_outputs(items, output: Path, confidence: float, dry_run: bool):
        global _LAST_SUMMARY
        result = base_build_outputs(items, output, confidence, dry_run)
        if _enabled() and not dry_run and _LAST_SESSION is not None:
            _LAST_SUMMARY = _write_shadow_evidence(items, output, _LAST_SESSION)
            module.HYBRID_EMBEDDING_SUMMARY = dict(_LAST_SUMMARY)
            coverage = float(_LAST_SUMMARY.get("confident_coverage", 0.0))
            agreement = _LAST_SUMMARY.get("agreement_with_sorter")
            agreement_text = "n/a" if agreement is None else f"{float(agreement):.1%}"
            print(
                f"Hybrid shadow evidence: {coverage:.1%} confident coverage | "
                f"{agreement_text} agreement with sorter | routing disabled"
            )
        return result

    def build_result(session):
        result = base_build_result(session)
        summary = dict(getattr(module, "HYBRID_EMBEDDING_SUMMARY", {}) or {})
        result["hybrid_embeddings"] = summary
        return result

    def render_markdown(result: dict[str, Any]) -> str:
        text = base_render_markdown(result)
        section = _benchmark_markdown_section(result.get("hybrid_embeddings") or {})
        if not section:
            return text
        marker = "\n## Provider timing\n"
        if marker in text:
            return text.replace(marker, section + "## Provider timing\n", 1)
        return text + section

    module.ensure_requirements = ensure_requirements
    module.select_photo_sample = select_photo_sample
    module.build_outputs = build_outputs
    module.HYBRID_EMBEDDING_SUMMARY = {}
    benchmark_module.build_result = build_result
    benchmark_module.render_markdown = render_markdown
    module.render_benchmark_markdown = render_markdown
    _install_cli_flags(module)
