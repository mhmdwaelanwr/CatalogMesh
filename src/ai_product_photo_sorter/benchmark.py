"""Benchmark instrumentation for Product Sorter.

Benchmark mode wraps the stable processing engine instead of duplicating it. Each
run is isolated under ``<output>/benchmarks/run_<timestamp>`` so cached batches
from normal operations cannot silently make a benchmark look faster than it is.
The report is deterministic and never makes an extra AI request.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BENCHMARK_ENV = "PRODUCT_SORTER_BENCHMARK"
_TRUE = {"1", "true", "yes", "on"}
_ACTIVE: "BenchmarkSession | None" = None


@dataclass
class BatchMetric:
    provider: str
    model: str
    photos: int
    elapsed_seconds: float
    success: bool
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""


@dataclass
class BenchmarkSession:
    source: Path
    base_output: Path
    run_output: Path
    label: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    started_monotonic: float = field(default_factory=time.perf_counter)
    cpu_started: float = field(default_factory=time.process_time)
    hardware_start: dict[str, Any] = field(default_factory=dict)
    batches: list[BatchMetric] = field(default_factory=list)
    encoded_images: int = 0
    encoded_bytes: int = 0
    encode_seconds: float = 0.0
    return_code: int | None = None


def benchmark_enabled() -> bool:
    return os.getenv(BENCHMARK_ENV, "").strip().lower() in _TRUE


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _fmt_bytes(value: int | float | None) -> str:
    size = float(max(0, value or 0))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TiB"


def _peak_memory_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            )
            return int(counters.PeakWorkingSetSize) if ok else None
        except Exception:
            return None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except Exception:
        return None


def _gpu_snapshot() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        rows = []
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 4:
                continue
            rows.append(
                {
                    "name": parts[0],
                    "memory_total_mib": _as_int(parts[1]),
                    "memory_used_mib": _as_int(parts[2]),
                    "utilization_percent": _as_int(parts[3]),
                }
            )
        return rows
    except Exception:
        return []


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def hardware_snapshot() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "logical_cpus": os.cpu_count() or 0,
        "gpu": _gpu_snapshot(),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _quality_score(output: Path) -> float | None:
    path = output / "quality_score.txt"
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("accuracy="):
                value = line.split("=", 1)[1].strip().rstrip("%")
                return float(value) / 100.0
    except (OSError, ValueError):
        pass
    return None


def _usage_facts(output: Path) -> dict[str, Any]:
    rows = _read_csv(output / "api_usage.csv")
    return {
        "records": len(rows),
        "input_tokens": sum(_as_int(row.get("input_tokens")) for row in rows),
        "output_tokens": sum(_as_int(row.get("output_tokens")) for row in rows),
        "estimated_cost": sum(float(row.get("estimated_cost", 0) or 0) for row in rows),
    }


def _source_bytes(source: Path, status_rows: list[dict[str, str]]) -> int:
    total = 0
    for row in status_rows:
        name = row.get("filename", "")
        if not name:
            continue
        try:
            total += (source / name).stat().st_size
        except OSError:
            pass
    return total


def build_result(session: BenchmarkSession) -> dict[str, Any]:
    wall = max(0.000001, time.perf_counter() - session.started_monotonic)
    cpu = max(0.0, time.process_time() - session.cpu_started)
    status_rows = _read_csv(session.run_output / "processing_status.csv")
    completed = sum(1 for row in status_rows if row.get("status") == "completed")
    pending = max(0, len(status_rows) - completed)
    usage = _usage_facts(session.run_output)
    successful = [batch for batch in session.batches if batch.success]
    failed = [batch for batch in session.batches if not batch.success]
    ai_seconds = sum(batch.elapsed_seconds for batch in session.batches)
    providers: dict[str, dict[str, Any]] = {}
    for batch in session.batches:
        key = f"{batch.provider}:{batch.model}"
        row = providers.setdefault(
            key,
            {
                "provider": batch.provider,
                "model": batch.model,
                "calls": 0,
                "failed_calls": 0,
                "seconds": 0.0,
                "photo_slots": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        )
        row["calls"] += 1
        row["failed_calls"] += 0 if batch.success else 1
        row["seconds"] += batch.elapsed_seconds
        row["photo_slots"] += batch.photos
        row["input_tokens"] += batch.input_tokens
        row["output_tokens"] += batch.output_tokens

    return {
        "schema_version": 1,
        "label": session.label,
        "started_at": session.started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "return_code": session.return_code,
        "source": str(session.source),
        "run_output": str(session.run_output),
        "photos_selected": len(status_rows),
        "photos_completed": completed,
        "photos_pending": pending,
        "source_bytes": _source_bytes(session.source, status_rows),
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "photos_per_second": completed / wall if completed else 0.0,
        "seconds_per_photo": wall / completed if completed else None,
        "logical_provider_calls": len(session.batches),
        "successful_provider_calls": len(successful),
        "failed_provider_calls": len(failed),
        "ai_call_seconds": ai_seconds,
        "image_encode_calls": session.encoded_images,
        "encoded_image_bytes": session.encoded_bytes,
        "image_encode_seconds": session.encode_seconds,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "estimated_cost": usage["estimated_cost"],
        "quality_accuracy": _quality_score(session.run_output),
        "peak_process_memory_bytes": _peak_memory_bytes(),
        "hardware_start": session.hardware_start,
        "hardware_end": hardware_snapshot(),
        "providers": sorted(providers.values(), key=lambda row: (row["provider"], row["model"])),
        "notes": [
            "The benchmark uses the real Product Sorter processing pipeline and an isolated output directory.",
            "Smart Markdown reporting is disabled during benchmark mode so its optional final AI narrative call cannot skew timing or token totals.",
            "Logical provider calls count wrapper-level batch calls. Retries performed inside a provider call are included in elapsed time but are not counted separately.",
            "Image encode calls can exceed unique photo count because neighboring batches intentionally overlap by one image.",
            "Quality accuracy is only present when --ground-truth is supplied.",
        ],
    }


def render_markdown(result: dict[str, Any]) -> str:
    quality = result.get("quality_accuracy")
    quality_text = f"{quality:.2%}" if isinstance(quality, (int, float)) else "Not measured"
    peak = result.get("peak_process_memory_bytes")
    seconds_per_photo = result.get("seconds_per_photo")
    lines = [
        "# Product Sorter Benchmark Report",
        "",
        f"> Generated {result['finished_at']} · isolated real-pipeline benchmark",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Photos selected | {result['photos_selected']} |",
        f"| Photos completed | {result['photos_completed']} |",
        f"| Dataset size | {_fmt_bytes(result['source_bytes'])} |",
        f"| Wall time | {_fmt_duration(result['wall_seconds'])} |",
        f"| Average time / completed photo | {seconds_per_photo:.3f} s |" if seconds_per_photo is not None else "| Average time / completed photo | n/a |",
        f"| Throughput | {result['photos_per_second']:.4f} photos/s |",
        f"| Logical provider calls | {result['logical_provider_calls']} |",
        f"| Failed provider calls | {result['failed_provider_calls']} |",
        f"| AI call wall time | {_fmt_duration(result['ai_call_seconds'])} |",
        f"| Image encode wall time | {_fmt_duration(result['image_encode_seconds'])} |",
        f"| Encoded image payload | {_fmt_bytes(result['encoded_image_bytes'])} |",
        f"| Input / output tokens | {result['input_tokens']} / {result['output_tokens']} |",
        f"| Estimated cost | {result['estimated_cost']:.6f} |",
        f"| Quality accuracy | {quality_text} |",
        f"| Peak process memory | {_fmt_bytes(peak) if peak is not None else 'Unavailable'} |",
        "",
        "## Provider timing",
        "",
        "| Provider | Model | Calls | Failed | Photo slots | Time | Input tokens | Output tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if result["providers"]:
        for row in result["providers"]:
            lines.append(
                f"| {row['provider']} | {row['model']} | {row['calls']} | {row['failed_calls']} | "
                f"{row['photo_slots']} | {row['seconds']:.3f} s | {row['input_tokens']} | {row['output_tokens']} |"
            )
    else:
        lines.append("| — | — | 0 | 0 | 0 | 0 s | 0 | 0 |")

    hardware = result.get("hardware_start", {})
    lines += [
        "",
        "## Environment",
        "",
        f"- Platform: `{hardware.get('platform', 'unknown')}`",
        f"- Python: `{hardware.get('python', 'unknown')}`",
        f"- Machine: `{hardware.get('machine', 'unknown')}`",
        f"- Processor: `{hardware.get('processor', 'unknown')}`",
        f"- Logical CPUs: `{hardware.get('logical_cpus', 0)}`",
    ]
    gpus = hardware.get("gpu") or []
    if gpus:
        for index, gpu in enumerate(gpus, 1):
            lines.append(
                f"- GPU {index}: `{gpu.get('name', 'unknown')}` · {gpu.get('memory_total_mib', 0)} MiB VRAM"
            )
    else:
        lines.append("- NVIDIA GPU snapshot: unavailable or not applicable")

    lines += [
        "",
        "## Methodology and caveats",
        "",
    ]
    lines += [f"- {note}" for note in result.get("notes", [])]
    lines += [
        "- Compare models only with the same dataset, image count, batch size, machine, network conditions, and application version.",
        "- Cloud-provider benchmarks include network latency. Local-provider benchmarks, once a local adapter is configured, should be reported separately.",
        "",
        "## Artifacts",
        "",
        "- `benchmark.json` — machine-readable result",
        "- `BENCHMARK_REPORT.md` — this report",
        "- Normal Product Sorter output files — evidence from the measured run",
        "",
    ]
    return "\n".join(lines)


def write_reports(session: BenchmarkSession) -> tuple[Path, Path, dict[str, Any]]:
    if not session.run_output.is_dir():
        raise RuntimeError("benchmark output was not initialized by the processing engine")
    result = build_result(session)
    json_path = session.run_output / "benchmark.json"
    md_path = session.run_output / "BENCHMARK_REPORT.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    history_path = session.run_output.parent / "history.jsonl"
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    latest_path = session.run_output.parent / "latest.txt"
    latest_path.write_text(str(md_path), encoding="utf-8")
    return md_path, json_path, result


def _record_batch(
    provider: str,
    model: str,
    photos: int,
    elapsed: float,
    success: bool,
    usage: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    if _ACTIVE is None:
        return
    usage = usage or {}
    _ACTIVE.batches.append(
        BatchMetric(
            provider=provider,
            model=model,
            photos=photos,
            elapsed_seconds=elapsed,
            success=success,
            input_tokens=_as_int(usage.get("input_tokens")),
            output_tokens=_as_int(usage.get("output_tokens")),
            error=error[:500],
        )
    )


def _strip_benchmark_args(argv: list[str]) -> tuple[list[str], bool | None, str]:
    remaining = [argv[0]]
    enabled: bool | None = None
    label = ""
    index = 1
    while index < len(argv):
        value = argv[index]
        if value == "--benchmark":
            enabled = True
        elif value == "--no-benchmark":
            enabled = False
        elif value == "--benchmark-label":
            index += 1
            if index >= len(argv):
                raise SystemExit("--benchmark-label requires a value")
            label = argv[index]
        else:
            remaining.append(value)
        index += 1
    return remaining, enabled, label


def apply_benchmark(module: Any) -> None:
    """Patch benchmark mode into the compatibility-preserved engine."""
    base_parse_args = module.parse_args
    base_call_gemini = module.call_gemini
    base_call_rest_pool = module.call_rest_pool
    base_compress = module.compressed_image_bytes
    base_main = module.main

    def parse_args(env_file: Path) -> argparse.Namespace:
        global _ACTIVE
        original = list(sys.argv)
        remaining, explicit, label = _strip_benchmark_args(original)
        sys.argv[:] = remaining
        try:
            try:
                args = base_parse_args(env_file)
            except SystemExit as exc:
                if exc.code == 0 and any(flag in original for flag in ("-h", "--help")):
                    print(
                        "\nBenchmark Center:\n"
                        "  --benchmark              Measure a fresh isolated real-pipeline run\n"
                        "  --no-benchmark           Disable benchmark mode\n"
                        "  --benchmark-label TEXT   Optional label stored in the report"
                    )
                raise
        finally:
            sys.argv[:] = original

        enabled = benchmark_enabled() if explicit is None else explicit
        os.environ[BENCHMARK_ENV] = "true" if enabled else "false"
        setattr(args, "benchmark", enabled)
        setattr(args, "benchmark_label", label)
        if enabled:
            source = args.source.expanduser().resolve()
            base_output = (args.output or source.parent / "Sorted_Products").expanduser().resolve()
            stamp = datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
            run_output = base_output / "benchmarks" / stamp
            args.output = run_output
            if hasattr(args, "md_report"):
                args.md_report = False
            os.environ["PRODUCT_SORTER_MD_REPORT"] = "false"
            _ACTIVE = BenchmarkSession(
                source=source,
                base_output=base_output,
                run_output=run_output,
                label=label,
                hardware_start=hardware_snapshot(),
            )
        else:
            _ACTIVE = None
        return args

    def compressed_image_bytes(path: Path) -> bytes:
        started = time.perf_counter()
        data = base_compress(path)
        if _ACTIVE is not None:
            _ACTIVE.encoded_images += 1
            _ACTIVE.encoded_bytes += len(data)
            _ACTIVE.encode_seconds += time.perf_counter() - started
        return data

    def call_gemini(pool: Any, model: str, photos: list[Any], catalog: str, max_retries: int, live_progress: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = base_call_gemini(pool, model, photos, catalog, max_retries, live_progress)
        except Exception as exc:
            _record_batch("gemini", model, len(photos), time.perf_counter() - started, False, error=str(exc))
            raise
        _record_batch("gemini", model, len(photos), time.perf_counter() - started, True, getattr(pool, "last_usage", {}))
        return result

    def call_rest_pool(pool: Any, photos: list[Any], catalog: str, max_retries: int, live_progress: Any = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = base_call_rest_pool(pool, photos, catalog, max_retries, live_progress)
        except Exception as exc:
            _record_batch(getattr(pool, "name", "rest"), getattr(pool, "model", ""), len(photos), time.perf_counter() - started, False, error=str(exc))
            raise
        _record_batch(
            getattr(pool, "name", "rest"),
            getattr(pool, "model", ""),
            len(photos),
            time.perf_counter() - started,
            True,
            getattr(pool, "last_usage", {}),
        )
        return result

    def main() -> int:
        global _ACTIVE
        code = 1
        try:
            code = base_main()
            return code
        finally:
            session = _ACTIVE
            if session is not None:
                session.return_code = code
                try:
                    if not session.run_output.is_dir():
                        continue_reporting = False
                    else:
                        continue_reporting = True
                    if continue_reporting:
                        md_path, json_path, result = write_reports(session)
                        print("\nBenchmark result")
                        print(f"Photos: {result['photos_completed']}/{result['photos_selected']}")
                        print(f"Wall time: {_fmt_duration(result['wall_seconds'])}")
                        print(f"Average: {result['seconds_per_photo']:.3f} s/photo" if result['seconds_per_photo'] is not None else "Average: n/a")
                        print(f"Provider calls: {result['logical_provider_calls']} ({result['failed_provider_calls']} failed)")
                        print(f"Benchmark report: {md_path}")
                        print(f"Benchmark JSON: {json_path}")
                        if hasattr(module, "append_log"):
                            module.append_log(session.run_output, "BENCHMARK_WRITTEN", f"path={md_path.name}")
                except Exception as exc:
                    print(f"Benchmark report could not be written: {exc}", file=sys.stderr)
                finally:
                    _ACTIVE = None

    module.parse_args = parse_args
    module.compressed_image_bytes = compressed_image_bytes
    module.call_gemini = call_gemini
    module.call_rest_pool = call_rest_pool
    module.main = main
    module.hardware_snapshot = hardware_snapshot
    module.render_benchmark_markdown = render_markdown
