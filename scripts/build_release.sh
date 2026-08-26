#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
python3 -m venv .build-venv
source .build-venv/bin/activate
python -m pip install -U pip build pyinstaller
python -m pip install -e .
python -m build
pyinstaller --clean packaging/pyinstaller/product_sorter.spec
