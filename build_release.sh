#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .build-venv
source .build-venv/bin/activate
python -m pip install -U pip build pyinstaller
python -m pip install -r requirements.txt
python -m build
pyinstaller --clean product_sorter.spec
