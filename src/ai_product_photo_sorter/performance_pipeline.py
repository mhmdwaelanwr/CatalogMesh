"""Safe performance pipeline for image preparation.

Provider inference and SQLite commits remain sequential because Product Sorter's
classification context and crash-safe operation state are order-sensitive. This
module parallelizes only the independent CPU/I/O stage that prepares API JPEGs
for the *current* batch, then lets the existing provider path consume those bytes
from the shared LRU cache.
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

DEFAULT_WORKERS = "auto"
DEFAULT_MEMORY_MB = 512
MAX_WORKERS = 16
_TRUE = {"1", "true", "yes", "on"}


def _configured_workers() -> int:
    raw = os.getenv("PRODUCT_SORTER_PREPROCESS_WORKERS", DEFAULT_WORKERS).strip().lower()
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
    raw = os.getenv("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES", "24").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES must be an integer") from exc
    if not 0 <= value <= 512:
        raise ValueError("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES must be between 0 and 512")
    return value


def _preflight_error() -> str:
    try:
        _configured_workers()
        _memory_budget_mb()
        _cache_entries()
    except ValueError as exc:
        return f"Performance pipeline configuration error: {exc}"
    return ""


def _batch_signature(photos: list[Any]) -> tuple[tuple[str, int, int], ...]:
    signature = []
    for photo in photos:
        path = Path(photo.path)
        stat = path.stat()
        signature.append((str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(signature)


def _memory_safe_workers(module: Any, photos: list[Any], desired: int) -> int:
    """Cap concurrency using a conservative decoded-pixel memory estimate."""
    if desired <= 1 or len(photos) <= 1:
        return max(1, min(desired or 1, len(photos) or 1))
    image_cls = getattr(module, "Image", None)
    if image_cls is None:
        return 1

    largest_decoded = 0
    try:
        for photo in photos:
            with image_cls.open(Path(photo.path)) as image:
                width, height = image.size
            # RGB operations can temporarily hold more than three bytes/pixel.
            # Four bytes/pixel is still an estimate, so the default budget is
            # deliberately conservative and configurable.
            largest_decoded = max(largest_decoded, int(width) * int(height) * 4)
    except Exception:
        # If even cheap header inspection is unreliable, prefer sequential work;
        # the normal encoder will later produce the canonical input error.
        return 1

    if largest_decoded <= 0:
        return 1
    budget = _memory_budget_mb() * 1024 * 1024
    memory_cap = max(1, budget // largest_decoded)
    return max(1, min(desired, int(memory_cap), len(photos)))


class BatchPreprocessor:
    """Warm the shared encoded-image cache once per logical batch."""

    def __init__(self, module: Any):
        self.module = module
        self._lock = threading.Lock()
        self._warmed: OrderedDict[tuple[tuple[str, int, int], ...], None] = OrderedDict()
        self.stats: dict[str, Any] = {
            "batches": 0,
            "images": 0,
            "seconds": 0.0,
            "parallel_batches": 0,
            "sequential_batches": 0,
            "skipped_cached_batches": 0,
            "skipped_cache_capacity": 0,
            "failures": 0,
            "max_workers_used": 0,
            "configured_workers": os.getenv("PRODUCT_SORTER_PREPROCESS_WORKERS", DEFAULT_WORKERS),
            "memory_budget_mb": None,
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
        desired = _configured_workers()
        if desired == 0:
            return
        cache_entries = _cache_entries()
        unique_images = len({str(Path(photo.path).resolve()) for photo in photos})
        # Prewarming is useful only if the complete batch can remain in cache
        # until the provider consumes it. Otherwise it can create extra work.
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
                        executor.submit(self.module.compressed_image_bytes, Path(photo.path)): Path(photo.path)
                        for photo in photos
                    }
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            raise RuntimeError(
                                f"Image preprocessing failed for {futures[future].name}: {exc}"
                            ) from exc
        except Exception:
            with self._lock:
                self.stats["failures"] += 1
            raise

        elapsed = time.perf_counter() - started
        self._remember(signature)
        with self._lock:
            self.stats["batches"] += 1
            self.stats["images"] += len(photos)
            self.stats["seconds"] += elapsed
            self.stats["memory_budget_mb"] = _memory_budget_mb()
            self.stats["max_workers_used"] = max(int(self.stats["max_workers_used"]), workers)
            if workers > 1:
                self.stats["parallel_batches"] += 1
            else:
                self.stats["sequential_batches"] += 1


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
            os.environ["PRODUCT_SORTER_PREPROCESS_WORKERS"] = str(known.preprocess_workers)
        if known.preprocess_memory_mb is not None:
            os.environ["PRODUCT_SORTER_PREPROCESS_MEMORY_MB"] = str(known.preprocess_memory_mb)
        if known.image_cache_entries is not None:
            os.environ["PRODUCT_SORTER_IMAGE_CACHE_ENTRIES"] = str(known.image_cache_entries)

        try:
            sys.argv = [original_argv[0], *remaining]
            args = base_parse_args(env_file)
        finally:
            sys.argv = original_argv
        args.preprocess_workers = os.getenv("PRODUCT_SORTER_PREPROCESS_WORKERS", DEFAULT_WORKERS)
        return args

    module.parse_args = parse_args


def apply_performance_pipeline(module: Any) -> None:
    """Install memory-aware preprocessing without changing inference ordering."""
    if getattr(module, "_PERFORMANCE_PIPELINE_INSTALLED", False):
        return
    module._PERFORMANCE_PIPELINE_INSTALLED = True

    base_ensure_requirements = module.ensure_requirements
    base_call_gemini = module.call_gemini
    base_call_rest_pool = module.call_rest_pool
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

    def call_gemini(pool, model, photos, catalog, max_retries, live_progress=None):
        preprocessor.warm(photos)
        return base_call_gemini(pool, model, photos, catalog, max_retries, live_progress)

    def call_rest_pool(pool, photos, catalog, max_retries, live_progress=None):
        preprocessor.warm(photos)
        return base_call_rest_pool(pool, photos, catalog, max_retries, live_progress)

    module.ensure_requirements = ensure_requirements
    module.call_gemini = call_gemini
    module.call_rest_pool = call_rest_pool
    _install_cli_flags(module)
