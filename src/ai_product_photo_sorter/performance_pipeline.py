"""Safe, measurable image-preprocessing acceleration.

Provider inference, product ordering, SQLite commits, and output mutation remain
sequential because Product Sorter's context and crash-safe resume state are
order-sensitive. This module parallelizes only the independent stage that opens,
normalizes, resizes, and JPEG-encodes photos for the current provider batch.

Prepared bytes are consumed through the existing bounded image cache, so the
provider code and classification contract remain unchanged.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import benchmark as benchmark_module

DEFAULT_WORKERS = "auto"
DEFAULT_MEMORY_MB = 512
DEFAULT_CACHE_ENTRIES = 24
MAX_WORKERS = 16


def _raw_workers() -> str:
    return os.getenv("PRODUCT_SORTER_PREPROCESS_WORKERS", DEFAULT_WORKERS).strip().lower()


def _configured_workers() -> int:
    raw = _raw_workers()
    if raw in {"off", "false", "disabled", "0"}:
        return 0
    if raw in {"", "auto"}:
        return max(1, min(4, os.cpu_count() or 1))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "PRODUCT_SORTER_PREPROCESS_WORKERS must be auto, off, or an integer from 1 to 16"
        ) from exc
    if not 1 <= value <= MAX_WORKERS:
        raise ValueError("PRODUCT_SORTER_PREPROCESS_WORKERS must be between 1 and 16")
    return value


def _memory_budget_mb() -> int:
    raw = os.getenv("PRODUCT_SORTER_PREPROCESS_MEMORY_MB", str(DEFAULT_MEMORY_MB)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("PRODUCT_SORTER_PREPROCESS_MEMORY_MB must be an integer") from exc
    if not 128 <= value <= 8192:
        raise ValueError("PRODUCT_SORTER_PREPROCESS_MEMORY_MB must be between 128 and 8192")
    return value


def _cache_entries() -> int:
    raw = os.getenv(
        "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES", str(DEFAULT_CACHE_ENTRIES)
    ).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES must be an integer") from exc
    if not 0 <= value <= 512:
        raise ValueError("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES must be between 0 and 512")
    return value


def _validate_configuration() -> None:
    _configured_workers()
    _memory_budget_mb()
    _cache_entries()


def _preflight_error() -> str:
    try:
        _validate_configuration()
    except ValueError as exc:
        return f"Performance pipeline configuration error: {exc}"
    return ""


def _batch_signature(photos: list[Any]) -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    for photo in photos:
        path = Path(photo.path)
        stat = path.stat()
        signature.append(
            (str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns))
        )
    return tuple(signature)


def _memory_safe_workers(module: Any, photos: list[Any], desired: int) -> int:
    """Cap concurrency using a conservative decoded-image memory estimate."""
    if not photos:
        return 0
    if desired <= 1 or len(photos) <= 1:
        return 1

    image_cls = getattr(module, "Image", None)
    if image_cls is None:
        return 1

    largest_estimated_bytes = 0
    try:
        for photo in photos:
            with image_cls.open(Path(photo.path)) as image:
                width, height = image.size
            # Decode + RGB conversion + resize/JPEG buffers can coexist briefly.
            # Eight bytes/pixel is deliberately conservative; this is a safety
            # limiter, not a memory-usage claim.
            largest_estimated_bytes = max(
                largest_estimated_bytes, int(width) * int(height) * 8
            )
    except Exception:
        # Header inspection is optimization-only. Fall back to one worker and let
        # the canonical image loader later produce the real input error.
        return 1

    if largest_estimated_bytes <= 0:
        return 1
    budget_bytes = _memory_budget_mb() * 1024 * 1024
    memory_cap = max(1, budget_bytes // largest_estimated_bytes)
    return max(1, min(desired, int(memory_cap), len(photos)))


def _stats_snapshot(stats: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(stats)
    seconds = float(snapshot.get("seconds", 0.0) or 0.0)
    images = int(snapshot.get("images", 0) or 0)
    snapshot["images_per_second"] = images / seconds if seconds > 0 else None
    snapshot["configured_workers"] = _raw_workers() or DEFAULT_WORKERS
    snapshot["resolved_workers"] = _configured_workers()
    snapshot["memory_budget_mb"] = _memory_budget_mb()
    snapshot["image_cache_entries"] = _cache_entries()
    return snapshot


def _benchmark_counters() -> tuple[Any, tuple[int, int, float] | None]:
    """Snapshot legacy benchmark encode counters before optimization-only prewarm.

    Benchmark Center historically counts image-byte requests made by the provider
    path. Prewarming intentionally performs those encodes earlier, so allowing the
    instrumentation wrapper to count both prewarm and later cache consumption
    would make before/after benchmark history incomparable. Dedicated
    ``preprocess_pipeline`` metrics record the physical prewarm work instead.
    """
    session = getattr(benchmark_module, "_ACTIVE", None)
    if session is None:
        return None, None
    return session, (
        int(getattr(session, "encoded_images", 0)),
        int(getattr(session, "encoded_bytes", 0)),
        float(getattr(session, "encode_seconds", 0.0)),
    )


def _restore_benchmark_counters(
    session: Any,
    counters: tuple[int, int, float] | None,
) -> None:
    if session is None or counters is None:
        return
    if getattr(benchmark_module, "_ACTIVE", None) is not session:
        return
    session.encoded_images, session.encoded_bytes, session.encode_seconds = counters


class BatchPreprocessor:
    """Warm the shared encoded-image cache once per logical provider batch."""

    def __init__(self, module: Any):
        self.module = module
        self._lock = threading.Lock()
        self._warmed: OrderedDict[
            tuple[tuple[str, int, int], ...], None
        ] = OrderedDict()
        self.stats: dict[str, Any] = {
            "batches": 0,
            "images": 0,
            "seconds": 0.0,
            "parallel_batches": 0,
            "sequential_batches": 0,
            "skipped_disabled": 0,
            "skipped_cached_batches": 0,
            "skipped_cache_capacity": 0,
            "failures": 0,
            "max_workers_used": 0,
        }

    def _remember(self, signature: tuple[tuple[str, int, int], ...]) -> None:
        with self._lock:
            self._warmed[signature] = None
            self._warmed.move_to_end(signature)
            while len(self._warmed) > 128:
                self._warmed.popitem(last=False)

    def warm(self, photos: list[Any]) -> None:
        if not photos:
            return
        _validate_configuration()
        desired = _configured_workers()
        if desired == 0:
            with self._lock:
                self.stats["skipped_disabled"] += 1
            return

        cache_entries = _cache_entries()
        unique_images = len({str(Path(photo.path).resolve()) for photo in photos})
        # Prewarming helps only when the current batch can remain resident until
        # the provider consumes it. Otherwise this could duplicate work.
        if cache_entries < unique_images:
            with self._lock:
                self.stats["skipped_cache_capacity"] += 1
            return

        signature = _batch_signature(photos)
        with self._lock:
            if signature in self._warmed:
                self.stats["skipped_cached_batches"] += 1
                self._warmed.move_to_end(signature)
                return

        workers = _memory_safe_workers(self.module, photos, desired)
        benchmark_session, benchmark_before = _benchmark_counters()
        started = time.perf_counter()
        try:
            if workers <= 1:
                for photo in photos:
                    self.module.compressed_image_bytes(Path(photo.path))
            else:
                with ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="product-sorter-image-preprocess",
                ) as executor:
                    futures = {
                        executor.submit(
                            self.module.compressed_image_bytes, Path(photo.path)
                        ): Path(photo.path)
                        for photo in photos
                    }
                    for future in as_completed(futures):
                        path = futures[future]
                        try:
                            future.result()
                        except Exception as exc:
                            raise RuntimeError(
                                f"Image preprocessing failed for {path.name}: {exc}"
                            ) from exc
        except Exception:
            with self._lock:
                self.stats["failures"] += 1
            raise
        finally:
            _restore_benchmark_counters(benchmark_session, benchmark_before)

        elapsed = max(0.0, time.perf_counter() - started)
        self._remember(signature)
        with self._lock:
            self.stats["batches"] += 1
            self.stats["images"] += len(photos)
            self.stats["seconds"] += elapsed
            self.stats["max_workers_used"] = max(
                int(self.stats["max_workers_used"]), workers
            )
            if workers > 1:
                self.stats["parallel_batches"] += 1
            else:
                self.stats["sequential_batches"] += 1


def _print_help() -> None:
    print(
        "\nPerformance / safe preprocessing:\n"
        "  --preprocess-workers VALUE     auto, off, or 1..16 (default auto)\n"
        "  --preprocess-memory-mb N       memory safety budget, 128..8192 MiB\n"
        "  --image-cache-entries N        encoded-image LRU entries, 0..512\n"
        "\nOnly image preparation is parallelized. Provider inference, grouping, "
        "SQLite commits, and output mutation remain ordered."
    )


def _install_cli_flags(module: Any) -> None:
    base_parse_args = module.parse_args

    def parse_args(env_file: Path):
        original_argv = list(sys.argv)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--preprocess-workers")
        parser.add_argument("--preprocess-memory-mb", type=int)
        parser.add_argument("--image-cache-entries", type=int)
        known, remaining = parser.parse_known_args(original_argv[1:])

        if known.preprocess_workers is not None:
            os.environ["PRODUCT_SORTER_PREPROCESS_WORKERS"] = str(
                known.preprocess_workers
            )
        if known.preprocess_memory_mb is not None:
            os.environ["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"] = str(
                known.preprocess_memory_mb
            )
        if known.image_cache_entries is not None:
            os.environ["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"] = str(
                known.image_cache_entries
            )

        try:
            _validate_configuration()
        except ValueError as exc:
            raise SystemExit(f"Performance pipeline configuration error: {exc}") from exc

        try:
            sys.argv = [original_argv[0], *remaining]
            args = base_parse_args(env_file)
        except SystemExit as exc:
            if exc.code == 0 and any(flag in original_argv for flag in ("-h", "--help")):
                _print_help()
            raise
        finally:
            sys.argv = original_argv

        args.preprocess_workers = _raw_workers() or DEFAULT_WORKERS
        args.preprocess_memory_mb = _memory_budget_mb()
        args.image_cache_entries = _cache_entries()
        return args

    module.parse_args = parse_args


def _benchmark_markdown_section(stats: dict[str, Any]) -> str:
    if not stats:
        return ""
    throughput = stats.get("images_per_second")
    throughput_text = (
        "n/a" if throughput is None else f"{float(throughput):.2f} images/s"
    )
    return "\n".join(
        [
            "",
            "## Safe preprocessing pipeline",
            "",
            f"- Configured workers: `{stats.get('configured_workers', 'auto')}`",
            f"- Resolved worker limit: `{stats.get('resolved_workers', 0)}`",
            f"- Maximum workers actually used: `{stats.get('max_workers_used', 0)}`",
            f"- Memory safety budget: `{stats.get('memory_budget_mb', 0)} MiB`",
            f"- Image-cache capacity: `{stats.get('image_cache_entries', 0)} entries`",
            f"- Preprocessed images: `{stats.get('images', 0)}`",
            f"- Preprocessing time: `{float(stats.get('seconds', 0.0)):.3f}s`",
            f"- Measured preprocessing throughput: `{throughput_text}`",
            f"- Parallel batches: `{stats.get('parallel_batches', 0)}`",
            f"- Sequential safety fallbacks: `{stats.get('sequential_batches', 0)}`",
            f"- Cache-capacity skips: `{stats.get('skipped_cache_capacity', 0)}`",
            "- Inference/SQLite/output ordering: `unchanged and sequential`",
            "",
        ]
    )


def apply_performance_pipeline(module: Any) -> None:
    """Install memory-aware preprocessing without changing inference ordering."""
    if getattr(module, "_PERFORMANCE_PIPELINE_INSTALLED", False):
        return
    module._PERFORMANCE_PIPELINE_INSTALLED = True

    base_ensure_requirements = module.ensure_requirements
    base_call_gemini = module.call_gemini
    base_call_rest_pool = module.call_rest_pool
    base_build_result = benchmark_module.build_result
    base_render_markdown = benchmark_module.render_markdown

    preprocessor = BatchPreprocessor(module)
    module.PREPROCESS_PIPELINE_STATS = preprocessor.stats

    def ensure_requirements() -> bool:
        if not base_ensure_requirements():
            return False
        error = _preflight_error()
        if error:
            print(error, file=sys.stderr)
            return False
        return True

    def call_gemini(
        pool: Any,
        model: str,
        photos: list[Any],
        catalog: str,
        max_retries: int,
        live_progress: Any = None,
    ):
        preprocessor.warm(photos)
        return base_call_gemini(
            pool, model, photos, catalog, max_retries, live_progress
        )

    def call_rest_pool(
        pool: Any,
        photos: list[Any],
        catalog: str,
        max_retries: int,
        live_progress: Any = None,
    ):
        preprocessor.warm(photos)
        return base_call_rest_pool(
            pool, photos, catalog, max_retries, live_progress
        )

    def build_result(session: Any) -> dict[str, Any]:
        result = base_build_result(session)
        result["preprocess_pipeline"] = _stats_snapshot(preprocessor.stats)
        return result

    def render_markdown(result: dict[str, Any]) -> str:
        text = base_render_markdown(result)
        return text + _benchmark_markdown_section(
            result.get("preprocess_pipeline") or {}
        )

    module.ensure_requirements = ensure_requirements
    module.call_gemini = call_gemini
    module.call_rest_pool = call_rest_pool
    module.preprocess_pipeline_snapshot = lambda: _stats_snapshot(preprocessor.stats)
    benchmark_module.build_result = build_result
    benchmark_module.render_markdown = render_markdown
    _install_cli_flags(module)
