#!/usr/bin/env python3
"""Launch the packaged Windows app, navigate it, and capture GUI evidence.

The smoke test deliberately targets ``ProductSorterPro.exe`` rather than the
source Python launcher.  PyInstaller one-file executables can create a bootloader
parent plus a child process that owns the real Tk window, so window discovery is
process-tree aware and does not bind automation to the launcher PID only.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

if sys.platform != "win32":
    raise SystemExit("gui_smoke_windows.py must run on Windows")

import psutil
import pyautogui
import win32gui
import win32process
from pywinauto import Desktop


WORKSPACES = (
    ("operation", ("Operation setup", "Setup"), 70),
    ("models", ("Models & API keys", "API"), 205),
    ("results", ("Results & activity", "Results"), 345),
    ("benchmark", ("Benchmark",), 465),
    ("environment", ("Environment",), 575),
    ("reports", ("Reports",), 675),
    ("about", ("About",), 760),
)


def _brightness(image: Image.Image) -> float:
    sample = image.convert("RGB").resize((1, 1))
    return sum(ImageStat.Stat(sample).mean) / 3.0


def _window_image(window) -> Image.Image:
    rect = window.rectangle()
    width = max(1, rect.right - rect.left)
    height = max(1, rect.bottom - rect.top)
    try:
        return pyautogui.screenshot(region=(rect.left, rect.top, width, height)).convert("RGB")
    except Exception:
        return window.capture_as_image().convert("RGB")


def _save_window(window, path: Path) -> dict[str, Any]:
    image = _window_image(window)
    image.save(path)
    return {
        "file": path.name,
        "width": image.width,
        "height": image.height,
        "brightness": round(_brightness(image), 2),
    }


def _matching_descendant(
    window,
    titles: tuple[str, ...],
    control_types: tuple[str, ...] = ("TabItem", "Button"),
):
    wanted = {title.casefold() for title in titles}
    for control_type in control_types:
        try:
            controls = window.descendants(control_type=control_type)
        except Exception:
            controls = []
        for control in controls:
            try:
                text = control.window_text().strip()
            except Exception:
                continue
            if text.casefold() in wanted:
                return control
    try:
        controls = window.descendants()
    except Exception:
        return None
    for control in controls:
        try:
            text = control.window_text().strip()
        except Exception:
            continue
        if text.casefold() in wanted:
            return control
    return None


def _select_workspace(window, titles: tuple[str, ...], fallback_x: int) -> str:
    control = _matching_descendant(window, titles, ("TabItem",))
    if control is not None:
        try:
            control.click_input()
            time.sleep(0.45)
            return "uia"
        except Exception:
            pass

    # Tk/ttk controls are not exposed consistently through UI Automation on all
    # Windows/Python combinations. The release window has a fixed header/tab
    # layout, so keep a deterministic relative-coordinate fallback.
    rect = window.rectangle()
    pyautogui.click(rect.left + fallback_x, rect.top + 118)
    time.sleep(0.45)
    return "coordinate-fallback"


def _theme_button(window):
    return _matching_descendant(window, ("Light mode", "Dark mode"), ("Button",))


def _click_theme(window) -> str:
    button = _theme_button(window)
    if button is not None:
        try:
            button.click_input()
            time.sleep(0.7)
            return "uia"
        except Exception:
            pass
    rect = window.rectangle()
    # Theme button sits immediately to the left of the language selector.
    pyautogui.click(rect.right - 245, rect.top + 70)
    time.sleep(0.7)
    return "coordinate-fallback"


def _ensure_theme(window, desired: str) -> str:
    before = _window_image(window)
    is_dark = _brightness(before) < 128
    already = (desired == "dark" and is_dark) or (desired == "light" and not is_dark)
    if already:
        return "already-active"

    method = _click_theme(window)
    after = _window_image(window)
    after_dark = _brightness(after) < 128
    ok = (desired == "dark" and after_dark) or (desired == "light" and not after_dark)
    if not ok:
        raise RuntimeError(f"theme switch to {desired!r} did not change the rendered window as expected")
    return method


def _fit_window(window) -> dict[str, int]:
    screen = pyautogui.size()
    width = max(980, min(1240, screen.width - 30))
    height = max(700, min(860, screen.height - 60))
    width = min(width, max(980, screen.width - 10))
    height = min(height, max(700, screen.height - 35))
    try:
        window.move_window(x=8, y=8, width=width, height=height, repaint=True)
        time.sleep(0.5)
    except Exception:
        pass
    return {
        "screen_width": screen.width,
        "screen_height": screen.height,
        "target_width": width,
        "target_height": height,
    }


def _candidate_pids(launcher_pid: int, exe: Path, launched_epoch: float) -> list[int]:
    pids: set[int] = {launcher_pid}
    try:
        root = psutil.Process(launcher_pid)
        pids.update(child.pid for child in root.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # A PyInstaller child can briefly outlive/re-parent from its bootloader.
    # Include freshly created processes with the same executable/name as a safe
    # fallback, while excluding older unrelated processes on a reused machine.
    expected_name = exe.name.casefold()
    expected_path = str(exe.resolve()).casefold()
    for process in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        try:
            info = process.info
            if float(info.get("create_time") or 0) < launched_epoch - 3:
                continue
            name = str(info.get("name") or "").casefold()
            path = str(info.get("exe") or "").casefold()
            if name == expected_name or path == expected_path:
                pids.add(int(info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
            continue
    return sorted(pids)


def _enum_windows(candidate_pids: set[int] | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def callback(hwnd, _extra):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if candidate_pids is not None and pid not in candidate_pids:
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            records.append(
                {
                    "handle": int(hwnd),
                    "pid": int(pid),
                    "title": win32gui.GetWindowText(hwnd),
                    "class_name": win32gui.GetClassName(hwnd),
                    "visible": bool(win32gui.IsWindowVisible(hwnd)),
                    "enabled": bool(win32gui.IsWindowEnabled(hwnd)),
                    "rect": [int(left), int(top), int(right), int(bottom)],
                    "width": int(max(0, right - left)),
                    "height": int(max(0, bottom - top)),
                }
            )
        except Exception:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return records


def _window_score(record: dict[str, Any]) -> tuple[int, int, int]:
    title = str(record.get("title") or "").casefold()
    class_name = str(record.get("class_name") or "").casefold()
    visible = bool(record.get("visible"))
    substantial = int(record.get("width", 0)) >= 600 and int(record.get("height", 0)) >= 400
    return (
        5 if "product sorter" in title else 0,
        3 if "tktop" in class_name else 0,
        2 if visible and substantial else 0,
    )


def _wrapper_for_handle(handle: int):
    # Prefer UIA for semantic control lookup. If Tk doesn't expose the handle to
    # UIA, Win32 is still enough for focus, sizing, capture and coordinate input.
    for backend in ("uia", "win32"):
        try:
            window = Desktop(backend=backend).window(handle=handle)
            if window.exists(timeout=1):
                return window, backend
        except Exception:
            continue
    return None, None


def _discover_window(
    launcher_pid: int,
    exe: Path,
    launched_epoch: float,
    timeout: float,
    output: Path,
) -> tuple[Any, str, list[int], list[dict[str, Any]]]:
    deadline = time.time() + timeout
    history: list[dict[str, Any]] = []
    last_records: list[dict[str, Any]] = []
    last_pids: list[int] = [launcher_pid]
    next_snapshot = 0.0

    while time.time() < deadline:
        last_pids = _candidate_pids(launcher_pid, exe, launched_epoch)
        last_records = _enum_windows(set(last_pids))
        candidates = [
            record
            for record in last_records
            if record["visible"] and record["width"] >= 400 and record["height"] >= 250
        ]
        candidates.sort(key=_window_score, reverse=True)

        for record in candidates:
            score = _window_score(record)
            if score[0] == 0 and score[1] == 0:
                continue
            wrapper, backend = _wrapper_for_handle(int(record["handle"]))
            if wrapper is not None:
                diagnostics = {
                    "launcher_pid": launcher_pid,
                    "candidate_pids": last_pids,
                    "selected": record,
                    "backend": backend,
                    "windows": last_records,
                    "history": history,
                }
                (output / "window-discovery.json").write_text(
                    json.dumps(diagnostics, indent=2), encoding="utf-8"
                )
                return wrapper, str(backend), last_pids, last_records

        now = time.time()
        if now >= next_snapshot:
            history.append(
                {
                    "elapsed_seconds": round(timeout - max(0.0, deadline - now), 2),
                    "candidate_pids": last_pids,
                    "windows": last_records,
                }
            )
            history = history[-12:]
            next_snapshot = now + 2.0
        time.sleep(0.4)

    diagnostics = {
        "launcher_pid": launcher_pid,
        "candidate_pids": last_pids,
        "windows": last_records,
        "history": history,
        "global_windows": _enum_windows(None),
    }
    (output / "window-discovery.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    try:
        pyautogui.screenshot().save(output / "desktop-failure.png")
    except Exception as exc:
        diagnostics["desktop_screenshot_error"] = f"{type(exc).__name__}: {exc}"
        (output / "window-discovery.json").write_text(
            json.dumps(diagnostics, indent=2), encoding="utf-8"
        )
    raise RuntimeError(
        f"main window did not appear within {timeout:.0f}s; "
        f"launcher={launcher_pid}, candidate_pids={last_pids}, windows={len(last_records)}"
    )


def _terminate_process_tree(launcher_pid: int) -> None:
    processes: list[psutil.Process] = []
    try:
        root = psutil.Process(launcher_pid)
        processes.extend(root.children(recursive=True))
        processes.append(root)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    for process in reversed(processes):
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(processes, timeout=2)
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _visual_score(actual: Path, baseline: Path) -> float:
    left = Image.open(actual).convert("RGB")
    right = Image.open(baseline).convert("RGB")
    if left.size != right.size:
        return 1.0
    diff = ImageChops.difference(left, right)
    rms = ImageStat.Stat(diff).rms
    return math.sqrt(sum(channel * channel for channel in rms) / len(rms)) / 255.0


def _compare_baselines(output: Path, baseline_dir: Path, threshold: float) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for actual in sorted(output.glob("*.png")):
        if actual.name in {"failure.png", "desktop-failure.png"}:
            continue
        baseline = baseline_dir / actual.name
        if not baseline.is_file():
            comparisons.append({"file": actual.name, "status": "missing-baseline", "score": None})
            continue
        score = _visual_score(actual, baseline)
        comparisons.append(
            {
                "file": actual.name,
                "status": "changed" if score > threshold else "match",
                "score": round(score, 6),
            }
        )
    return {
        "threshold": threshold,
        "baseline_dir": str(baseline_dir),
        "comparisons": comparisons,
        "changed": sum(1 for item in comparisons if item["status"] == "changed"),
    }


def _write_gallery(output: Path, screenshots: list[dict[str, Any]]) -> None:
    cards = []
    for item in screenshots:
        filename = html.escape(item["file"])
        label = html.escape(
            f"{item['theme'].title()} · {item['workspace'].replace('-', ' ').title()}"
        )
        cards.append(
            f'<figure><a href="{filename}"><img src="{filename}" loading="lazy"></a>'
            f'<figcaption>{label}</figcaption></figure>'
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Product Sorter GUI Smoke Gallery</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0b1220;color:#e8eef8}}
header{{padding:24px 28px;border-bottom:1px solid #26364f}} h1{{margin:0 0 6px;font-size:24px}} p{{margin:0;color:#94a3b8}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px;padding:22px}}
figure{{margin:0;background:#111c2e;border:1px solid #26364f;border-radius:12px;overflow:hidden}} img{{display:block;width:100%;height:auto;background:#fff}}
figcaption{{padding:11px 14px;font-weight:600}} a{{color:inherit;text-decoration:none}}
</style></head><body><header><h1>Product Sorter GUI Smoke Gallery</h1><p>Captured from the packaged Windows executable.</p></header><main>{''.join(cards)}</main></body></html>"""
    (output / "gallery.html").write_text(document, encoding="utf-8")


def run(
    exe: Path,
    output: Path,
    timeout: float,
    baseline_dir: Path | None,
    threshold: float,
) -> dict[str, Any]:
    if not exe.is_file():
        raise FileNotFoundError(f"built executable not found: {exe}")
    output.mkdir(parents=True, exist_ok=True)
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.08

    started = time.perf_counter()
    launched_epoch = time.time()
    launcher = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    window = None
    backend = ""
    screenshots: list[dict[str, Any]] = []
    interaction_methods: dict[str, str] = {}
    candidate_pids: list[int] = [launcher.pid]
    try:
        window, backend, candidate_pids, _records = _discover_window(
            launcher.pid, exe, launched_epoch, timeout, output
        )

        title = window.window_text().strip()
        try:
            window.set_focus()
        except Exception:
            pass
        display = _fit_window(window)

        # Start with Light for review consistency, then repeat every workspace in Dark.
        for theme in ("light", "dark"):
            interaction_methods[f"theme:{theme}"] = _ensure_theme(window, theme)
            for index, (slug, titles, fallback_x) in enumerate(WORKSPACES, 1):
                method = _select_workspace(window, titles, fallback_x)
                interaction_methods[f"tab:{theme}:{slug}"] = method
                path = output / f"{theme}-{index:02d}-{slug}.png"
                meta = _save_window(window, path)
                meta.update({"theme": theme, "workspace": slug, "navigation": method})
                screenshots.append(meta)

        _write_gallery(output, screenshots)
        result: dict[str, Any] = {
            "status": "passed",
            "executable": str(exe),
            "launcher_pid": launcher.pid,
            "candidate_pids": candidate_pids,
            "window_backend": backend,
            "window_title": title,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "display": display,
            "screenshots": screenshots,
            "interaction_methods": interaction_methods,
        }
        if baseline_dir is not None and baseline_dir.is_dir():
            result["visual_regression"] = _compare_baselines(output, baseline_dir, threshold)
        return result
    except Exception:
        if window is not None:
            try:
                window.print_control_identifiers(filename=str(output / "control-identifiers.txt"))
            except Exception:
                pass
            try:
                _save_window(window, output / "failure.png")
            except Exception:
                pass
        try:
            pyautogui.screenshot().save(output / "desktop-failure.png")
        except Exception:
            pass
        raise
    finally:
        if window is not None:
            try:
                window.close()
                time.sleep(0.5)
            except Exception:
                pass
        _terminate_process_tree(launcher.pid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("gui-artifacts"))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--visual-threshold", type=float, default=0.08)
    parser.add_argument("--fail-on-visual-diff", action="store_true")
    args = parser.parse_args()

    result_path = args.output / "gui-smoke-results.json"
    try:
        result = run(
            args.exe.resolve(),
            args.output.resolve(),
            args.timeout,
            args.baseline_dir,
            args.visual_threshold,
        )
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(result["error"], file=sys.stderr)
        return 2

    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    visual = result.get("visual_regression") or {}
    if args.fail_on_visual_diff and int(visual.get("changed", 0)) > 0:
        print(
            f"visual regression threshold exceeded in {visual['changed']} screenshot(s)",
            file=sys.stderr,
        )
        return 3
    print(f"GUI smoke passed: {len(result['screenshots'])} screenshots captured")
    print(f"Gallery: {args.output / 'gallery.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
