# Windows GUI Automation

Product Sorter's release workflow includes a packaged-executable GUI smoke test on Windows.

The purpose is to validate the same `ProductSorterPro.exe` artifact that is distributed to users rather than launching the source Python GUI.

## Pipeline

```text
Build Windows executable
        ↓
Upload ProductSorterPro-windows-x64 artifact
        ↓
Download that exact artifact in GUI smoke job
        ↓
Launch ProductSorterPro.exe
        ↓
Verify the main window appears
        ↓
Navigate all desktop workspaces
        ↓
Capture Light + Dark screenshots
        ↓
Close the application
        ↓
Upload screenshots, gallery, and JSON evidence
```

The workflow runs through the existing `build-and-release` pipeline, so it applies to pull requests, manual workflow dispatches, pushes to `main`, and release tags.

## What is exercised

The smoke script opens the packaged Windows application and captures every main workspace in both themes:

1. Operation setup
2. Models & API keys
3. Results & activity
4. Benchmark
5. Environment
6. Reports
7. About

That produces 14 normal screenshots per successful run.

The automation prefers Windows UI Automation through `pywinauto`. Tk/ttk controls are not exposed consistently by every Windows/Python combination, so tab/theme interactions include a deterministic relative-coordinate fallback. Screenshot capture uses PyAutoGUI/Pillow with a window-capture fallback.

## Artifacts

The `gui-screenshots-windows` workflow artifact contains:

```text
gui-artifacts/
├── light-01-operation.png
├── light-02-models.png
├── light-03-results.png
├── light-04-benchmark.png
├── light-05-environment.png
├── light-06-reports.png
├── light-07-about.png
├── dark-01-operation.png
├── dark-02-models.png
├── dark-03-results.png
├── dark-04-benchmark.png
├── dark-05-environment.png
├── dark-06-reports.png
├── dark-07-about.png
├── gallery.html
└── gui-smoke-results.json
```

If startup/navigation fails, the job also attempts to preserve `failure.png` and a `control-identifiers.txt` dump for diagnosis.

The packaged executable remains available separately in the existing `ProductSorterPro-windows-x64` artifact from the same workflow run.

## Visual regression foundation

The smoke runner already supports optional baseline comparison:

```powershell
python scripts/gui_smoke_windows.py `
  --exe gui-build/ProductSorterPro.exe `
  --output gui-artifacts `
  --baseline-dir tests/visual/baseline/windows `
  --visual-threshold 0.08
```

When `tests/visual/baseline/windows` exists, the workflow automatically records comparison results. Visual differences are intentionally **non-blocking** at first; the executable launch/navigation smoke itself is blocking.

After representative Windows screenshots are reviewed and approved, baseline images can be committed and `--fail-on-visual-diff` can be enabled with an agreed tolerance. This avoids turning font anti-aliasing or minor renderer differences into flaky required checks before a stable baseline exists.

## Local Windows run

Build the packaged application first:

```powershell
pyinstaller --clean --noconfirm packaging/pyinstaller/product_sorter.spec
python -m pip install pywinauto pyautogui pillow
python scripts/gui_smoke_windows.py --exe dist/ProductSorterPro.exe --output gui-artifacts
```

Open `gui-artifacts/gallery.html` to review all captured screens together.
