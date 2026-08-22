#!/usr/bin/env python3
"""Safely group product photos with Gemini while preserving originals."""

from __future__ import annotations

import argparse
import atexit
import csv
import getpass
import hashlib
import importlib.util
import io
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from i18n import confirm_language, tr
from model_catalog import default_model
from professional import (VERSION, OperationLock, backup_progress, clear_failure,
    ensure_failure_schema, estimate_work, evaluate_report, export_failures,
    export_usage, migrate_database, record_failure, record_usage, rotate_log)
from providers import configured_rest_providers
from secrets_store import load_into_environment

try:
    from PIL import Image, ImageOps
except ImportError:  # dependency wizard runs before image processing
    Image = None
    ImageOps = None

try:
    from google import genai
    from google.genai import types
except ImportError:  # allows --dry-run without the SDK
    genai = None
    types = None


IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
CATEGORIES = {
    "mouse", "keyboard", "headset", "speaker", "cable", "charger",
    "controller", "adapter", "microphone", "webcam", "other",
}
DEFAULT_ENV_FILE = Path(__file__).resolve().with_name(".env")
REQUIREMENTS_FILE = Path(__file__).resolve().with_name("requirements.txt")
REQUIRED_MODULES = {
    "Pillow": "PIL",
    "google-genai": "google.genai",
    "openpyxl": "openpyxl",
}
STOP_REQUESTED = threading.Event()

def request_stop(signum=None, frame=None) -> None:
    STOP_REQUESTED.set()


def non_interactive() -> bool:
    return os.getenv("PRODUCT_SORTER_NON_INTERACTIVE", "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Photo:
    path: Path
    taken_at: datetime


def load_api_keys() -> list[str]:
    """Load up to four unique Gemini keys without ever printing them."""
    candidates = [os.getenv(f"GEMINI_API_KEY_{index}", "").strip() for index in range(1, 5)]
    # Keep the old single-key setup working.
    candidates.append(os.getenv("GEMINI_API_KEY", "").strip())
    keys: list[str] = []
    for key in candidates:
        if key and key not in keys:
            keys.append(key)
    return keys[:4]


def validate_gemini_key(key: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
        headers={"x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return True, "ok"
    except Exception as exc:
        return False, str(exc)


class GeminiClientPool:
    """Rotate through API keys when a key is rate-limited or exhausted."""

    def __init__(self, keys: list[str]):
        self.clients = [genai.Client(api_key=key) for key in keys]
        self.index = 0
        self.last_usage: dict[str,int] = {}

    @property
    def client(self) -> Any:
        return self.clients[self.index]

    def rotate(self) -> bool:
        if len(self.clients) < 2:
            return False
        self.index = (self.index + 1) % len(self.clients)
        return True

    def add_key(self, key: str) -> None:
        """Add a temporary key entered interactively and select it immediately."""
        self.clients.append(genai.Client(api_key=key))
        self.index = len(self.clients) - 1


def request_new_api_key(progress: Any = None, provider: str = "Gemini") -> str:
    response_file=os.getenv("PRODUCT_SORTER_KEY_RESPONSE_FILE","").strip()
    if response_file:
        print(f"__PRODUCT_SORTER_KEY_REQUEST__:{provider}",flush=True)
        path=Path(response_file); deadline=time.monotonic()+600
        while time.monotonic()<deadline and not STOP_REQUESTED.is_set():
            if path.is_file():
                try:
                    value=path.read_text(encoding="utf-8").strip(); path.unlink(missing_ok=True)
                    return value
                except OSError: pass
            time.sleep(.2)
        return ""
    if non_interactive():
        return ""
    if progress:
        progress.pause()
    print(f"All configured {provider} keys reached their quota or rate limit.")
    try:
        return getpass.getpass(f"Enter a new {provider} API key to continue (hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    finally:
        if progress:
            progress.resume()


def internet_quality(latency_ms: float) -> str:
    if latency_ms < 300:
        return tr("excellent")
    if latency_ms < 700:
        return tr("good")
    if latency_ms < 1500:
        return tr("fair")
    return tr("weak")


def check_internet(timeout: float = 5.0) -> tuple[bool, float | None, str]:
    """Check connectivity and estimate quality from response latency."""
    request = urllib.request.Request(
        "https://www.google.com/generate_204",
        headers={"User-Agent": "product-sorter/1.0"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1)
        latency_ms = (time.perf_counter() - started) * 1000
        return True, latency_ms, internet_quality(latency_ms)
    except Exception:
        return False, None, tr("disconnected")


def require_internet(output: Path) -> bool:
    """Verify connectivity before an API batch; allow retry or safe exit."""
    while True:
        connected, latency_ms, quality = check_internet()
        if connected:
            assert latency_ms is not None
            print(tr("internet", quality=quality, ms=f"{latency_ms:.0f}"))
            append_log(output, "INTERNET_CHECK", f"quality={quality}; latency_ms={latency_ms:.0f}")
            return True
        print(tr("offline"), file=sys.stderr)
        append_log(output, "INTERNET_CHECK", "quality=offline")
        if non_interactive():
            return False
        try:
            choice = input(tr("retry_or_quit")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            choice = "q"
        if choice == "q":
            return False


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class LiveProgress:
    """A lightweight live progress bar with a learned ETA countdown."""

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, total: int, completed: int):
        self.total = total
        self.completed = completed
        self.session_initial = completed
        self.api_seconds = 0.0
        self.batch_started = 0.0
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.batch_started = time.monotonic()
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def finish(self, completed: int) -> None:
        elapsed = max(0.001, time.monotonic() - self.batch_started)
        self.api_seconds += elapsed
        self.completed = completed
        self.batch_started = time.monotonic()
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._render(0, final=True)
        print()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._clear_line()

    def pause(self) -> None:
        self._paused.set()
        self._clear_line()

    def resume(self) -> None:
        self._paused.clear()

    def note(self, message: str) -> None:
        self.pause()
        print(message)
        self.resume()

    def _run(self) -> None:
        tick = 0
        while not self._stop.wait(1):
            if not self._paused.is_set():
                self._render(tick)
                tick += 1

    def _eta(self) -> float | None:
        processed_here = self.completed - self.session_initial
        if processed_here <= 0 or self.api_seconds <= 0:
            return None
        seconds_per_photo = self.api_seconds / processed_here
        estimate = seconds_per_photo * (self.total - self.completed)
        return max(0, estimate - (time.monotonic() - self.batch_started))

    def _render(self, tick: int, final: bool = False) -> None:
        percent = 100 if not self.total else min(100, int(self.completed * 100 / self.total))
        width = 24
        filled = min(width, int(width * percent / 100))
        bar = "█" * filled + "░" * (width - filled)
        remaining = max(0, self.total - self.completed)
        eta = self._eta()
        eta_text = format_duration(eta) if eta is not None else tr("calculating")
        spinner = "✓" if final else self.SPINNER[tick % len(self.SPINNER)]
        text = (
            f"{spinner} [{bar}] {percent:3d}% | {self.completed}/{self.total} | "
            f"{tr('progress_remaining', count=remaining)} | {tr('progress_eta', eta=eta_text)}"
        )
        print(f"\r{text:<115}", end="", flush=True)

    @staticmethod
    def _clear_line() -> None:
        print("\r" + " " * 120 + "\r", end="", flush=True)


def load_env_file(path: Path) -> bool:
    """Load simple KEY=VALUE settings without executing the file."""
    if not path.is_file():
        return False
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            print(f"Warning: ignored invalid .env line {line_number}", file=sys.stderr)
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            print(f"Warning: ignored invalid .env name on line {line_number}", file=sys.stderr)
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(name, value)
    return True


def preload_env() -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    known, _ = parser.parse_known_args()
    env_path = known.env_file.expanduser().resolve()
    load_env_file(env_path)
    return env_path


def env_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


def missing_requirements() -> list[str]:
    missing: list[str] = []
    for package, module in REQUIRED_MODULES.items():
        try:
            available = importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(package)
    return missing


def install_requirements(path: Path = REQUIREMENTS_FILE) -> bool:
    if not path.is_file():
        print(f"ملف requirements.txt غير موجود: {path}", file=sys.stderr)
        return False
    print(f"\n{tr('installing')}\n")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(path)],
            check=False,
        )
    except OSError as exc:
        print(f"تعذر تشغيل pip: {exc}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(tr("install_failed"), file=sys.stderr)
        return False
    print(tr("install_success"))
    return True


def ensure_requirements() -> bool:
    missing = missing_requirements()
    if not missing:
        print(tr("requirements_ok"))
        return True
    print(f"\n{tr('missing_libs')}")
    for package in missing:
        print(f"- {package}")
    if non_interactive():
        print("Run start.sh or install requirements.txt first.", file=sys.stderr)
        return False
    print(f"\n[1] {tr('install_now')}")
    print(f"[2] {tr('exit')}")
    while True:
        try:
            choice = input("اختر 1 أو 2 [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print()
            choice = "2"
        if choice == "1":
            if not install_requirements():
                return False
            print(tr("restart_next"))
            os.execv(sys.executable, [sys.executable, *sys.argv])
            return False
        if choice == "2":
            print("تم الخروج من دون تثبيت أي شيء.")
            return False
        print("اختيار غير صحيح. أدخل 1 أو 2.")


def parse_args(env_file: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Group product photos using Gemini API")
    source_default = env_path("PRODUCT_SOURCE")
    parser.add_argument("--env-file", type=Path, default=env_file, help="Settings file; defaults to .env beside script")
    parser.add_argument("--source", type=Path, default=source_default, required=source_default is None,
                        help="Folder containing JPG files")
    parser.add_argument("--output", type=Path, default=env_path("PRODUCT_OUTPUT"),
                        help="Output folder; defaults beside source")
    parser.add_argument("--prices", type=Path, default=env_path("PRICES_FILE"),
                        help="Optional .xlsx product-price catalog")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", default_model("gemini") or "gemini-3.6-flash"))
    parser.add_argument("--limit", type=int, default=os.getenv("PHOTO_LIMIT") or None,
                        help="Only analyze the first N photos")
    parser.add_argument("--batch-size", type=int, default=os.getenv("BATCH_SIZE", "6"), choices=range(3, 9))
    parser.add_argument("--confidence", type=float, default=os.getenv("CONFIDENCE", "0.75"))
    parser.add_argument("--max-retries", type=int, default=os.getenv("MAX_RETRIES", "5"))
    parser.add_argument("--dry-run", action="store_true", help="Inspect only; do not call Gemini or create links")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild output links/report from cached responses")
    parser.add_argument("--retry-failed", action="store_true", help="Retry only previously failed images")
    parser.add_argument("--ground-truth", type=Path, help="Expected CSV used to score result quality")
    parser.add_argument("--validate-keys", action="store_true", help="Validate configured provider keys")
    parser.add_argument("--version", action="version", version=f"Product Sorter {VERSION}")
    parser.add_argument("--non-interactive", action="store_true", help="Use safe defaults without terminal prompts")
    return parser.parse_args()


def exif_datetime(path: Path) -> datetime:
    try:
        with Image.open(path) as image:
            raw = image.getexif().get(36867)  # DateTimeOriginal
            if raw:
                return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    match = re.search(r"(\d{8})_(\d{6})", path.name)
    if match:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    return datetime.fromtimestamp(path.stat().st_mtime)


def discover(source: Path, limit: int | None) -> list[Photo]:
    photos = [Photo(p, exif_datetime(p)) for p in source.iterdir()
              if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    photos.sort(key=lambda p: (p.taken_at, p.path.name))
    return photos[:limit] if limit else photos


def select_photo_sample(photos: list[Photo], configured_limit: int | None) -> list[Photo] | None:
    total = len(photos)
    quick_sample = min(total, configured_limit or 50)
    if non_interactive():
        return photos[:configured_limit] if configured_limit else photos
    print(f"\n{tr('total_photos', count=total)}")
    print(f"[1] {tr('all_photos')}")
    print(f"[2] {tr('quick_sample', count=quick_sample)}")
    print(f"[3] {tr('custom_count')}")
    print(f"[4] {tr('exit')}")
    while True:
        try:
            choice = input("اختر 1 أو 2 أو 3 أو 4 [2]: ").strip() or "2"
        except (EOFError, KeyboardInterrupt):
            print()
            choice = "2"
        if choice == "1":
            return photos
        if choice == "2":
            return photos[:quick_sample]
        if choice == "3":
            while True:
                try:
                    raw = input(tr("how_many", total=total)).strip()
                    count = int(raw)
                    if 1 <= count <= total:
                        return photos[:count]
                except (ValueError, EOFError):
                    pass
                except KeyboardInterrupt:
                    print()
                    return None
                print(f"العدد غير صحيح. أدخل رقمًا من 1 إلى {total}.")
        if choice == "4":
            return None
        print("اختيار غير صحيح. أدخل 1 أو 2 أو 3 أو 4.")


def connect_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS batches (
        batch_key TEXT PRIMARY KEY, model TEXT NOT NULL, filenames TEXT NOT NULL,
        response_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
    db.commit()
    migrate_database(db)
    return db


def append_log(output: Path, event: str, details: str = "") -> None:
    """Append a human-readable event without storing API keys."""
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
    suffix = f" | {details}" if details else ""
    log_path = output / "run_history.log"
    rotate_log(log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} | {event}{suffix}\n")


def processed_filenames(db: sqlite3.Connection) -> set[str]:
    processed: set[str] = set()
    for response in cached_batches(db):
        processed.update(
            str(item.get("filename", "")) for item in response.get("items", [])
        )
    return processed


def progress_count(db: sqlite3.Connection, photos: list[Photo]) -> int:
    known = {photo.path.name for photo in photos}
    return len(known & processed_filenames(db))


def batch_already_processed(db: sqlite3.Connection, photos: list[Photo]) -> bool:
    """Allow safe resume even when the selected provider model has changed."""
    completed = processed_filenames(db)
    return bool(photos) and all(photo.path.name in completed for photo in photos)


def write_status_files(output: Path, photos: list[Photo], db: sqlite3.Connection) -> None:
    """Maintain exact completed/pending lists after every saved batch."""
    completed = processed_filenames(db)
    output.mkdir(parents=True, exist_ok=True)

    csv_path = output / "processing_status.csv"
    csv_temp = output / "processing_status.csv.tmp"
    with csv_temp.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["position", "filename", "taken_at", "status"]
        )
        writer.writeheader()
        for position, photo in enumerate(photos, 1):
            writer.writerow({
                "position": position,
                "filename": photo.path.name,
                "taken_at": photo.taken_at.isoformat(sep=" "),
                "status": "completed" if photo.path.name in completed else "pending",
            })
    os.replace(csv_temp, csv_path)

    for filename, want_completed in (
        ("completed_files.txt", True), ("pending_files.txt", False)
    ):
        path = output / filename
        temp = output / f"{filename}.tmp"
        names = [
            photo.path.name for photo in photos
            if (photo.path.name in completed) == want_completed
        ]
        with temp.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(names))
            if names:
                handle.write("\n")
        os.replace(temp, path)


def choose_operation(output: Path, processed: int, total: int) -> tuple[str, Path]:
    remaining = max(0, total - processed)
    if non_interactive():
        return "resume", output
    print(tr("previous_status", done=processed, total=total, left=remaining))
    print(f"[1] {tr('continue_previous')}")
    print(f"[2] {tr('new_operation')}")
    print(f"[3] {tr('exit')}")
    while True:
        try:
            choice = input("Choose 1, 2, or 3 [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print()
            choice = "3"
        if choice == "1":
            return "resume", output
        if choice == "2":
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            return "new", output.with_name(f"{output.name}_New_{stamp}")
        if choice == "3":
            return "exit", output
        print("Invalid choice. Enter 1, 2, or 3.")


def batch_key(photos: list[Photo], model: str) -> str:
    digest = hashlib.sha256(model.encode())
    for photo in photos:
        st = photo.path.stat()
        digest.update(f"{photo.path.name}:{st.st_size}:{st.st_mtime_ns}".encode())
    return digest.hexdigest()


def load_catalog(path: Path | None) -> str:
    if not path:
        return ""
    try:
        import openpyxl
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        lines: list[str] = []
        seen: set[str] = set()
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                text = " | ".join(str(v).strip() for v in row if v not in (None, ""))
                if text and text not in seen:
                    seen.add(text)
                    lines.append(text)
        return "\n".join(lines)[:24000]
    except Exception as exc:
        print(f"Warning: could not read price catalog: {exc}", file=sys.stderr)
        return ""


def image_part(path: Path) -> Any:
    return types.Part.from_bytes(data=compressed_image_bytes(path), mime_type="image/jpeg")


def compressed_image_bytes(path: Path) -> bytes:
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()


def call_rest_provider(provider: Any, photos: list[Photo], catalog: str) -> dict[str, Any]:
    raw = provider.generate(prompt_for(photos, catalog), photos, compressed_image_bytes)
    return normalize_response(raw, photos)


def prompt_for(photos: list[Photo], catalog: str) -> str:
    listing = "\n".join(
        f"Image {i}: {p.path.name}, captured {p.taken_at.isoformat(sep=' ')}"
        for i, p in enumerate(photos, 1)
    )
    catalog_text = f"\nPossible catalog rows:\n{catalog}" if catalog else ""
    return f"""You classify consecutive photos of retail technology products.
Each product was usually photographed from the front and then the back, but a
product may have one, two, or more photos. Use object appearance, packaging,
brand/model text, and capture time. Never assume strict pairs.

{listing}
{catalog_text}

Return JSON only in this exact shape:
{{"items":[{{"filename":"exact filename","same_product_as_previous":false,
"category":"mouse|keyboard|headset|speaker|cable|charger|controller|adapter|microphone|webcam|other",
"view":"front|back|side|detail|unknown","brand":"", "model":"",
"catalog_match":"", "confidence":0.0, "reason":"short reason"}}]}}

Rules:
- Include every image exactly once and preserve the listed order.
- For the first image, same_product_as_previous must be false.
- Confidence is from 0 to 1.
- Read visible package text carefully; do not invent a model number.
- catalog_match must be an exact catalog row or empty.
"""


def normalize_response(raw: str, photos: list[Photo]) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    data = json.loads(text)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items")
    else:
        raise ValueError("Gemini response must be a JSON object or list")
    if not isinstance(items, list) or len(items) != len(photos):
        raise ValueError("Gemini response did not contain one item per image")
    expected = [p.path.name for p in photos]
    received = [str(item.get("filename", "")) for item in items]
    if received != expected:
        raise ValueError(f"Gemini returned unexpected filename order: {received}")
    for index, item in enumerate(items):
        item["same_product_as_previous"] = bool(item.get("same_product_as_previous", False)) if index else False
        category = str(item.get("category", "other")).lower()
        item["category"] = category if category in CATEGORIES else "other"
        try:
            item["confidence"] = max(0.0, min(1.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            item["confidence"] = 0.0
        for field in ("view", "brand", "model", "catalog_match", "reason"):
            item[field] = str(item.get(field, "")).strip()
    return {"items": items}


def call_gemini(pool: GeminiClientPool, model: str, photos: list[Photo], catalog: str,
                max_retries: int, live_progress: LiveProgress | None = None) -> dict[str, Any]:
    contents: list[Any] = [prompt_for(photos, catalog)]
    for index, photo in enumerate(photos, 1):
        contents.append(f"Image {index}: {photo.path.name}")
        contents.append(image_part(photo.path))
    quota_failures = 0
    other_failures = 0
    while True:
        try:
            response = pool.client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.1
                ),
            )
            usage=getattr(response,"usage_metadata",None)
            pool.last_usage={"input_tokens":int(getattr(usage,"prompt_token_count",0) or 0),"output_tokens":int(getattr(usage,"candidates_token_count",0) or 0)}
            return normalize_response(response.text, photos)
        except Exception as exc:
            message = str(exc)
            upper_message = message.upper()
            quota = "429" in message or "RESOURCE_EXHAUSTED" in message.upper()
            if quota:
                quota_failures += 1
                if quota_failures >= len(pool.clients):
                    new_key = request_new_api_key(live_progress,"Gemini")
                    if not new_key:
                        raise RuntimeError(
                            "No new API key was entered. Progress is saved; run the same "
                            "command later to continue."
                        ) from exc
                    pool.add_key(new_key)
                    message = tr("new_key_ok")
                    live_progress.note(message) if live_progress else print(message)
                    continue
                pool.rotate()
                message = tr("switch_key", current=pool.index + 1, total=len(pool.clients))
                live_progress.note(message) if live_progress else print(message)
                continue
            terminal = any(marker in upper_message for marker in (
                "400 ", "401 ", "403 ", "404 ", "INVALID_ARGUMENT", "UNAUTHENTICATED",
                "PERMISSION_DENIED", "NOT_FOUND",
            ))
            if terminal:
                raise RuntimeError(f"Gemini request cannot be retried with this model/configuration: {exc}") from exc
            if other_failures >= max_retries:
                raise RuntimeError(
                    "Gemini quota/error persisted. Progress is saved; run the same command later. "
                    f"Last error: {exc}"
                ) from exc
            delay = min(120, 2 ** other_failures * 2)
            other_failures += 1
            message = f"Gemini error; retrying in {delay}s ({other_failures}/{max_retries})"
            live_progress.note(message) if live_progress else print(message)
            time.sleep(delay)


def call_rest_pool(pool: Any, photos: list[Photo], catalog: str, max_retries: int,
                   live_progress: LiveProgress | None = None) -> dict[str, Any]:
    """Call OpenAI/Anthropic with quota-aware rotation across up to four keys."""
    quota_failures=0; other_failures=0
    while True:
        try:
            result=call_rest_provider(pool.client,photos,catalog)
            pool.last_usage=pool.client.last_usage
            return result
        except Exception as exc:
            message=str(exc); upper=message.upper()
            quota=any(marker in upper for marker in ("429","RATE_LIMIT","RATE LIMIT","RESOURCE_EXHAUSTED","QUOTA"))
            if quota:
                quota_failures+=1
                if quota_failures>=len(pool.clients):
                    new_key=request_new_api_key(live_progress,pool.name.title())
                    if not new_key:
                        raise RuntimeError(f"All {pool.name} keys are exhausted. Progress is saved; run again later to continue.") from exc
                    pool.add_key(new_key); quota_failures=0
                    note=f"New {pool.name} key accepted for this run."
                    live_progress.note(note) if live_progress else print(note)
                    continue
                pool.rotate(); note=f"Switching {pool.name} key: {pool.index+1}/{len(pool.clients)}"
                live_progress.note(note) if live_progress else print(note)
                continue
            if other_failures>=max_retries:
                raise RuntimeError(f"{pool.name} error persisted. Progress is saved. Last error: {exc}") from exc
            delay=min(120,2**other_failures*2); other_failures+=1
            note=f"{pool.name} error; retrying in {delay}s ({other_failures}/{max_retries})"
            live_progress.note(note) if live_progress else print(note); time.sleep(delay)


def cached_batches(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute("SELECT response_json FROM batches ORDER BY created_at, rowid").fetchall()
    return [json.loads(row[0]) for row in rows]


def merge_observations(photos: list[Photo], responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for response in responses:
        for item in response["items"]:
            name = item["filename"]
            current = observations.get(name)
            prior_relation = bool(current and current.get("same_product_as_previous"))
            if current is None or item["confidence"] > current["confidence"]:
                observations[name] = {**item, "same_product_as_previous": (
                    prior_relation or bool(item.get("same_product_as_previous"))
                )}
            elif current and item.get("same_product_as_previous"):
                current["same_product_as_previous"] = True
    merged = []
    for photo in photos:
        item = observations.get(photo.path.name)
        if item:
            merged.append({**item, "path": photo.path, "taken_at": photo.taken_at})
    return merged


def safe_name(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_.")
    return value[:70] or fallback


def build_outputs(items: list[dict[str, Any]], output: Path, confidence: float,
                  dry_run: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "classification_report.csv"
    product_number = 0
    current_folder = ""
    rows = []
    for index, item in enumerate(items):
        if index == 0 or not item["same_product_as_previous"]:
            product_number += 1
            label = "_".join(x for x in (item["brand"], item["model"]) if x)
            current_folder = f"Product_{product_number:04d}_{safe_name(label, item['category'])}"
        review = item["confidence"] < confidence or item["category"] == "other"
        destination_dir = output / ("Needs_Review" if review else item["category"]) / current_folder
        destination = destination_dir / item["path"].name
        if not dry_run:
            destination_dir.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                try:
                    os.link(item["path"], destination)
                except OSError:
                    destination.symlink_to(item["path"].resolve())
        rows.append({
            "filename": item["path"].name,
            "taken_at": item["taken_at"].isoformat(sep=" "),
            "product_group": current_folder,
            "category": item["category"], "view": item["view"],
            "brand": item["brand"], "model": item["model"],
            "catalog_match": item["catalog_match"],
            "confidence": item["confidence"],
            "status": "needs_review" if review else "classified",
            "reason": item["reason"],
        })
    if not dry_run:
        with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["filename"])
            writer.writeheader()
            writer.writerows(rows)
    print(f"Grouped {len(rows)} photos into {product_number} tentative products")
    if not dry_run:
        print(f"Report: {report_path}")


def main() -> int:
    STOP_REQUESTED.clear()
    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal,"SIGTERM"): signal.signal(signal.SIGTERM, request_stop)
    env_file = preload_env()
    if os.getenv("USE_KEYRING","").lower() in {"1","true","yes"}: load_into_environment()
    args = parse_args(env_file)
    if args.non_interactive:
        os.environ["PRODUCT_SORTER_NON_INTERACTIVE"] = "1"
    if env_file.is_file():
        print(f"Loaded settings from: {env_file}")
    else:
        print(f"Settings file not found: {env_file}", file=sys.stderr)
    if not non_interactive():
        confirm_language()
    if not ensure_requirements():
        return 2
    source = args.source.expanduser().resolve()
    if not source.is_dir():
        print(f"Source folder does not exist: {source}", file=sys.stderr)
        return 2
    if args.prices and (not args.prices.expanduser().is_file() or args.prices.suffix.lower() != ".xlsx"):
        print(f"Invalid price file: {args.prices}", file=sys.stderr)
        return 2
    output = (args.output or source.parent / "Sorted_Products").expanduser().resolve()
    if output == source or source in output.parents:
        print("Output must not be the source folder or inside it.", file=sys.stderr)
        return 2
    all_photos = discover(source, None)
    print(tr("found_photos", count=len(all_photos)))
    if not all_photos:
        return 0
    photos = select_photo_sample(all_photos, args.limit)
    if photos is None:
        print("Stopped before processing any photos.")
        return 0
    print(tr("selected_photos", selected=len(photos), total=len(all_photos)))
    if args.dry_run:
        for photo in photos[:10]:
            print(photo.taken_at.isoformat(sep=" "), photo.path.name)
        return 0
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "progress.sqlite3"
    previous_operation = db_path.exists()
    lock = OperationLock(output)
    if not lock.acquire():
        print("Another Product Sorter process is already using this output folder.", file=sys.stderr)
        return 2
    atexit.register(lock.release)
    if previous_operation:
        backup_progress(db_path)
    db = connect_db(db_path)
    ensure_failure_schema(db)
    if previous_operation and not args.rebuild:
        processed = progress_count(db, photos)
        action, selected_output = choose_operation(output, processed, len(photos))
        append_log(output, "STARTUP_CHOICE", f"action={action}; processed={processed}; total={len(photos)}")
        if action == "exit":
            write_status_files(output, photos, db)
            db.close()
            print("Stopped safely. Run the same command when you want to continue.")
            return 0
        if action == "new":
            db.close()
            output = selected_output
            output.mkdir(parents=True, exist_ok=True)
            db = connect_db(output / "progress.sqlite3")
            ensure_failure_schema(db)
            print(f"New operation output: {output}")
    if args.retry_failed:
        failed_names=set()
        for (raw,) in db.execute("SELECT filenames FROM failures"):
            failed_names.update(json.loads(raw))
        photos=[p for p in photos if p.path.name in failed_names]
        if not photos:
            print("No failed photos to retry."); return 0
    write_status_files(output, photos, db)
    print(f"Status list: {output / 'processing_status.csv'}")
    append_log(output, "RUN_STARTED", f"source={source}; total_photos={len(photos)}")
    if not args.rebuild:
        api_keys = load_api_keys()
        requested=[x.strip().lower() for x in os.getenv("AI_PROVIDERS",os.getenv("AI_PROVIDER","gemini")).split(",")]
        rest_providers=configured_rest_providers()
        pool = GeminiClientPool(api_keys) if api_keys and "gemini" in requested else None
        if not pool and not rest_providers:
            print("No configured AI provider key was found.", file=sys.stderr); return 2
        validate_keys = args.validate_keys or os.getenv("VALIDATE_KEYS", "true").lower() in {"1","true","yes"}
        if validate_keys:
            for index,key_value in enumerate(api_keys,1):
                ok,detail=validate_gemini_key(key_value); print(f"gemini key {index}: {'OK' if ok else 'FAILED'} {detail if not ok else ''}")
            for provider in rest_providers:
                for index,(ok,detail) in enumerate(provider.validate_all(),1):
                    print(f"{provider.name} key {index}: {'OK' if ok else 'FAILED'} {detail if not ok else ''}")
        estimate=estimate_work(len(photos),args.batch_size,float(os.getenv("COST_PER_REQUEST","0") or 0))
        print(f"Estimated API requests: {estimate['requests']} | Estimated cost: {estimate['estimated_cost']:.2f}")
        catalog = load_catalog(args.prices)
        live_progress = LiveProgress(len(photos), progress_count(db, photos))
        step = args.batch_size - 1
        for start in range(0, len(photos), step):
            if STOP_REQUESTED.is_set():
                append_log(output,"RUN_STOPPED","graceful stop requested"); print("Stop requested; progress is saved."); break
            batch = photos[start:start + args.batch_size]
            if len(batch) < 2 and start:
                break
            key = batch_key(batch, args.model)
            if batch_already_processed(db, batch) or db.execute("SELECT 1 FROM batches WHERE batch_key=?", (key,)).fetchone():
                print(f"Cached: {batch[0].path.name} … {batch[-1].path.name}")
                continue
            if not require_internet(output):
                append_log(output, "RUN_STOPPED", "internet unavailable; user chose exit")
                print("Stopped safely. Progress is saved.")
                return 0
            print(f"Analyzing {start + 1}–{min(start + len(batch), len(photos))}/{len(photos)}")
            live_progress.start()
            try:
                errors=[]; result=None; used_provider=None; used_model=None; usage={}; rest_by_name={p.name:p for p in rest_providers}
                for provider_name in requested:
                    if result is not None: break
                    if provider_name=="gemini" and pool:
                        try:
                            result=call_gemini(pool,args.model,batch,catalog,args.max_retries,live_progress); used_provider="gemini"; used_model=args.model; usage=pool.last_usage
                        except RuntimeError as exc: errors.append(f"gemini: {exc}")
                    elif provider_name in rest_by_name:
                        provider=rest_by_name[provider_name]
                        try:
                            live_progress.note(f"Trying provider: {provider.name}")
                            result=call_rest_pool(provider,batch,catalog,args.max_retries,live_progress); used_provider=provider.name; used_model=provider.model; usage=provider.last_usage
                        except Exception as exc: errors.append(f"{provider.name}: {exc}")
                if result is None: raise RuntimeError(" | ".join(errors))
            except RuntimeError as exc:
                live_progress.stop()
                record_failure(db,key,json.dumps([p.path.name for p in batch]),str(exc)); export_failures(db,output)
                append_log(output, "RUN_STOPPED", str(exc))
                print(str(exc), file=sys.stderr)
                return 1
            db.execute(
                "INSERT INTO batches VALUES (?, ?, ?, ?, ?)",
                (key, args.model, json.dumps([p.path.name for p in batch]),
                 json.dumps(result, ensure_ascii=False), datetime.now().isoformat()),
            )
            db.commit()
            if used_provider:
                record_usage(db,used_provider,used_model or "",int(usage.get("input_tokens",0) or 0),int(usage.get("output_tokens",0) or 0))
            clear_failure(db,key); export_failures(db,output)
            write_status_files(output, photos, db)
            live_progress.finish(progress_count(db, photos))
            append_log(
                output, "BATCH_SAVED",
                f"photos={batch[0].path.name} ... {batch[-1].path.name}"
            )
            if STOP_REQUESTED.is_set():
                append_log(output,"RUN_STOPPED","graceful stop completed after batch"); break
    items = merge_observations(photos, cached_batches(db))
    build_outputs(items, output, args.confidence, dry_run=False)
    export_usage(db,output)
    if args.ground_truth:
        score=evaluate_report(output/"classification_report.csv",args.ground_truth,output)
        print(f"Quality accuracy: {score:.2%}")
    append_log(output, "RUN_COMPLETED", f"classified_photos={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
