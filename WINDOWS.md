# CatalogMesh on Windows

CatalogMesh supports two practical Windows launch paths.

## Option 1 — Ready-to-run desktop build (recommended)

1. Open the latest GitHub Release.
2. Download `ProductSorterPro-windows-x64.zip`.
3. Extract the ZIP to a normal writable folder such as `Downloads\CatalogMesh`.
4. Double-click `ProductSorterPro.exe`.

The executable filename is retained for v3.x compatibility. The application display brand is **CatalogMesh**.

Windows SmartScreen may show a warning because the current release binaries are not code-signed yet. Use the Windows "More info" flow only when the file came from the official GitHub Release for this repository.

## Option 2 — Install from PyPI

Requirements: Python 3.10 or newer.

```powershell
py -m pip install --upgrade catalogmesh
catalogmesh-gui
```

If `catalogmesh-gui` is not found after installation, close and reopen PowerShell so the Python Scripts directory is refreshed in the current session.

You can also verify the installed package from PowerShell:

```powershell
py -m pip show catalogmesh
catalogmesh --help
```

The historical PyPI project name `ai-product-photo-sorter` remains a legacy v3.x identifier. New installs should use `catalogmesh`.

## Development build from main

```powershell
git clone https://github.com/mhmdwaelanwr/CatalogMesh.git
cd CatalogMesh
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -e .
catalogmesh-gui
```

## Safety when testing

For casual GUI testing, do not use production Shopify, Akeneo or Odoo credentials. Local scan, Review, SKU Match proposals, offline exports, Storage dry-runs and connector previews are enough to verify the desktop workflow without external catalog mutation.
