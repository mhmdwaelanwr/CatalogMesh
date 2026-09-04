#!/usr/bin/env python3
"""Smoke-test the packaged CatalogMesh Windows GUI across all 12 workspaces."""
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
    ("operation", ("Operation setup", "Setup")),
    ("models", ("Models & API keys", "API")),
    ("results", ("Results & activity", "Results")),
    ("review", ("Review",)),
    ("sku-match", ("SKU Match",)),
    ("exports", ("Exports",)),
    ("storage", ("Storage",)),
    ("automation", ("Automation",)),
    ("reports", ("Reports",)),
    ("benchmark", ("Benchmark",)),
    ("environment", ("Environment",)),
    ("about", ("About",)),
)
THEME_CENTER_FROM_RIGHT = 194
THEME_CENTER_Y = 79
THEME_BRIGHTNESS_DELTA = 3.0
THEME_IMAGE_DELTA = 0.01
THEME_BACKGROUND_DELTA = 8.0


def _brightness(image: Image.Image) -> float:
    sample = image.convert("RGB").resize((1, 1))
    return sum(ImageStat.Stat(sample).mean) / 3.0


def _image_delta(left: Image.Image, right: Image.Image) -> float:
    first = left.convert("RGB")
    second = right.convert("RGB")
    if first.size != second.size:
        return 1.0
    diff = ImageChops.difference(first, second)
    rms = ImageStat.Stat(diff).rms
    return math.sqrt(sum(channel * channel for channel in rms) / len(rms)) / 255.0


def _background_brightness(image: Image.Image) -> float:
    rgb = image.convert("RGB")
    inset = max(8, min(rgb.size) // 40)
    size = max(20, min(rgb.size) // 12)
    boxes = (
        (inset, inset, inset + size, inset + size),
        (rgb.width - inset - size, inset, rgb.width - inset, inset + size),
        (inset, rgb.height - inset - size, inset + size, rgb.height - inset),
        (rgb.width - inset - size, rgb.height - inset - size, rgb.width - inset, rgb.height - inset),
    )
    samples = [ImageStat.Stat(rgb.crop(box).resize((1, 1))).mean for box in boxes]
    return sum(sum(sample) / 3.0 for sample in samples) / len(samples)


def _window_image(window) -> Image.Image:
    try:
        image = window.capture_as_image().convert("RGB")
        if image.width > 100 and image.height > 100:
            return image
    except Exception:
        pass
    rect = window.rectangle()
    return pyautogui.screenshot(
        region=(rect.left, rect.top, max(1, rect.width()), max(1, rect.height()))
    ).convert("RGB")


def _matching_descendant(window, titles: tuple[str, ...], control_types: tuple[str, ...]):
    wanted = {title.casefold() for title in titles}
    for control_type in control_types:
        try:
            controls = window.descendants(control_type=control_type)
        except Exception:
            controls = []
        for control in controls:
            try:
                if control.window_text().strip().casefold() in wanted:
                    return control
            except Exception:
                continue
    try:
        controls = window.descendants()
    except Exception:
        return None
    for control in controls:
        try:
            if control.window_text().strip().casefold() in wanted:
                return control
        except Exception:
            continue
    return None


def _focus(window) -> None:
    try:
        window.set_focus()
    except Exception:
        pass


def _select_workspace(window, titles: tuple[str, ...], current_index: int, target_index: int) -> tuple[str, int]:
    # The v3.3 desktop UX hides Notebook tabs on wide screens and uses real ttk
    # sidebar buttons. Prefer those buttons; TabItem remains a compatibility path.
    control = _matching_descendant(window, titles, ("Button", "TabItem"))
    if control is not None:
        try:
            control.click_input()
            time.sleep(0.55)
            return "uia-sidebar", target_index
        except Exception:
            pass

    # Keyboard fallback stays independent of pixel coordinates and works whether
    # the sidebar or compact workspace selector is visible.
    _focus(window)
    steps = (target_index - current_index) % len(WORKSPACES)
    for _ in range(steps):
        pyautogui.hotkey("ctrl", "tab")
        time.sleep(0.12)
    time.sleep(0.45)
    return "keyboard-cycle", target_index


def _click_theme(window) -> str:
    button = _matching_descendant(window, ("Light mode", "Dark mode"), ("Button",))
    if button is not None:
        try:
            button.click_input()
            time.sleep(0.8)
            return "uia"
        except Exception:
            pass
    _focus(window)
    rect = window.rectangle()
    pyautogui.click(rect.right - THEME_CENTER_FROM_RIGHT, rect.top + THEME_CENTER_Y)
    time.sleep(0.9)
    return "coordinate-fallback"


def _ensure_theme(window, desired: str, output: Path) -> tuple[str, dict[str, Any]]:
    before = _window_image(window)
    before_brightness = _brightness(before)
    before_background = _background_brightness(before)
    is_dark = before_brightness < 128
    already = (desired == "dark" and is_dark) or (desired == "light" and not is_dark)
    if already:
        return "already-active", {
            "requested": desired,
            "success": True,
            "already_active": True,
            "brightness_before": round(before_brightness, 2),
            "background_before": round(before_background, 2),
            "warning": None,
        }

    method = _click_theme(window)
    after = _window_image(window)
    after_brightness = _brightness(after)
    after_background = _background_brightness(after)
    brightness_delta = abs(after_brightness - before_brightness)
    background_delta = abs(after_background - before_background)
    image_delta = _image_delta(before, after)
    success = (
        brightness_delta >= THEME_BRIGHTNESS_DELTA
        or image_delta >= THEME_IMAGE_DELTA
        or background_delta >= THEME_BACKGROUND_DELTA
    )
    warning = None if success else "visual change not detected"
    if warning:
        print(f"WARNING: theme validation for {desired!r}: {warning}", file=sys.stderr)
    before.save(output / f"theme-{desired}-before.png")
    after.save(output / f"theme-{desired}-after.png")
    return method, {
        "requested": desired,
        "success": success,
        "already_active": False,
        "warning": warning,
        "interaction": method,
        "brightness_before": round(before_brightness, 2),
        "brightness_after": round(after_brightness, 2),
        "brightness_delta": round(brightness_delta, 2),
        "image_delta": round(image_delta, 6),
        "background_before": round(before_background, 2),
        "background_after": round(after_background, 2),
        "background_delta": round(background_delta, 2),
    }


def _candidate_pids(launcher_pid: int, exe: Path, launched_epoch: float) -> list[int]:
    pids = {launcher_pid}
    try:
        root = psutil.Process(launcher_pid)
        pids.update(child.pid for child in root.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
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


def _enum_windows(candidate_pids: set[int]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def callback(hwnd, _extra):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid not in candidate_pids:
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            records.append({
                "handle": int(hwnd),
                "pid": int(pid),
                "title": win32gui.GetWindowText(hwnd),
                "class_name": win32gui.GetClassName(hwnd),
                "visible": bool(win32gui.IsWindowVisible(hwnd)),
                "width": int(max(0, right - left)),
                "height": int(max(0, bottom - top)),
            })
        except Exception:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return records


def _discover_window(launcher_pid: int, exe: Path, launched_epoch: float, timeout: float, output: Path):
    deadline = time.time() + timeout
    last: list[dict[str, Any]] = []
    pids = [launcher_pid]
    while time.time() < deadline:
        pids = _candidate_pids(launcher_pid, exe, launched_epoch)
        last = _enum_windows(set(pids))
        candidates = [record for record in last if record["visible"] and record["width"] >= 500 and record["height"] >= 300]
        candidates.sort(
            key=lambda record: (
                6 if "catalogmesh" in str(record["title"]).casefold() else 0,
                5 if "product sorter" in str(record["title"]).casefold() else 0,
                3 if "tk" in str(record["class_name"]).casefold() else 0,
                record["width"] * record["height"],
            ),
            reverse=True,
        )
        for record in candidates:
            for backend in ("uia", "win32"):
                try:
                    window = Desktop(backend=backend).window(handle=record["handle"])
                    if window.exists(timeout=1):
                        (output / "window-discovery.json").write_text(
                            json.dumps({"launcher_pid": launcher_pid, "candidate_pids": pids, "selected": record, "backend": backend, "windows": last}, indent=2),
                            encoding="utf-8",
                        )
                        return window, backend, pids
                except Exception:
                    continue
        time.sleep(0.4)
    (output / "window-discovery.json").write_text(
        json.dumps({"launcher_pid": launcher_pid, "candidate_pids": pids, "windows": last}, indent=2),
        encoding="utf-8",
    )
    raise RuntimeError(f"main CatalogMesh window did not appear within {timeout:.0f}s")


def _fit_window(window) -> dict[str, int]:
    screen = pyautogui.size()
    try:
        window.maximize()
        time.sleep(0.7)
    except Exception:
        pass
    rect = window.rectangle()
    return {
        "screen_width": screen.width,
        "screen_height": screen.height,
        "window_left": rect.left,
        "window_top": rect.top,
        "window_width": rect.width(),
        "window_height": rect.height(),
    }


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


def _compare_baselines(output: Path, baseline_dir: Path, threshold: float) -> dict[str, Any]:
    comparisons = []
    for actual in sorted(output.glob("light-*.png")) + sorted(output.glob("dark-*.png")):
        baseline = baseline_dir / actual.name
        if not baseline.is_file():
            comparisons.append({"file": actual.name, "status": "missing-baseline", "score": None})
            continue
        score = _image_delta(Image.open(actual), Image.open(baseline))
        comparisons.append({"file": actual.name, "status": "changed" if score > threshold else "match", "score": round(score, 6)})
    return {"threshold": threshold, "baseline_dir": str(baseline_dir), "comparisons": comparisons, "changed": sum(item["status"] == "changed" for item in comparisons)}


def _write_gallery(output: Path, screenshots: list[dict[str, Any]]) -> None:
    cards = []
    for item in screenshots:
        filename = html.escape(item["file"])
        label = html.escape(f"{item['theme'].title()} · {item['workspace'].replace('-', ' ').title()}")
        cards.append(f'<figure><a href="{filename}"><img src="{filename}" loading="lazy"></a><figcaption>{label}</figcaption></figure>')
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CatalogMesh GUI Smoke</title><style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0b1220;color:#e8eef8}}header{{padding:24px 28px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:18px;padding:22px}}figure{{margin:0;background:#111c2e;border:1px solid #26364f;border-radius:12px;overflow:hidden}}img{{display:block;width:100%;height:auto}}figcaption{{padding:11px 14px;font-weight:600}}</style></head><body><header><h1>CatalogMesh Windows GUI Smoke</h1><p>12 workflow workspaces captured from the packaged executable.</p></header><main>{''.join(cards)}</main></body></html>"""
    (output / "gallery.html").write_text(document, encoding="utf-8")


def run(exe: Path, output: Path, timeout: float, baseline_dir: Path | None, threshold: float) -> dict[str, Any]:
    if not exe.is_file():
        raise FileNotFoundError(f"built executable not found: {exe}")
    output.mkdir(parents=True, exist_ok=True)
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.08
    started = time.perf_counter()
    launched_epoch = time.time()
    launcher = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    window = None
    screenshots: list[dict[str, Any]] = []
    interactions: dict[str, str] = {}
    theme_validation: list[dict[str, Any]] = []
    try:
        window, backend, candidate_pids = _discover_window(launcher.pid, exe, launched_epoch, timeout, output)
        _focus(window)
        display = _fit_window(window)
        title = window.window_text().strip()
        current_index = 0

        for theme in ("light", "dark"):
            method, theme_result = _ensure_theme(window, theme, output)
            interactions[f"theme:{theme}"] = method
            theme_validation.append(theme_result)
            previous: Image.Image | None = None
            for index, (slug, titles) in enumerate(WORKSPACES):
                before = _window_image(window)
                nav_method, current_index = _select_workspace(window, titles, current_index, index)
                after = _window_image(window)
                delta = _image_delta(before, after)
                if index > 0 and delta < 0.001:
                    raise RuntimeError(f"workspace {slug!r} did not visibly activate (delta={delta:.6f})")
                if previous is not None and _image_delta(previous, after) < 0.001:
                    raise RuntimeError(f"workspace {slug!r} rendered the same image as the previous workspace")
                path = output / f"{theme}-{index + 1:02d}-{slug}.png"
                after.save(path)
                screenshots.append({
                    "file": path.name,
                    "theme": theme,
                    "workspace": slug,
                    "navigation": nav_method,
                    "activation_delta": round(delta, 6),
                    "width": after.width,
                    "height": after.height,
                    "brightness": round(_brightness(after), 2),
                })
                interactions[f"workspace:{theme}:{slug}"] = nav_method
                previous = after

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
            "workspace_count": len(WORKSPACES),
            "screenshots": screenshots,
            "interaction_methods": interactions,
            "theme_validation": theme_validation,
        }
        if baseline_dir is not None and baseline_dir.is_dir():
            result["visual_regression"] = _compare_baselines(output, baseline_dir, threshold)
        return result
    except Exception:
        if window is not None:
            try:
                _window_image(window).save(output / "failure.png")
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
        result = run(args.exe.resolve(), args.output.resolve(), args.timeout, args.baseline_dir, args.visual_threshold)
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(result["error"], file=sys.stderr)
        return 2
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    visual = result.get("visual_regression") or {}
    if args.fail_on_visual_diff and int(visual.get("changed", 0)) > 0:
        print(f"visual regression threshold exceeded in {visual['changed']} screenshot(s)", file=sys.stderr)
        return 3
    print(f"GUI smoke passed: {len(result['screenshots'])} screenshots captured across {result['workspace_count']} workspaces")
    print(f"Gallery: {args.output / 'gallery.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
