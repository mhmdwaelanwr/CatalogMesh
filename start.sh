#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements.txt
if [ ! -f .env ] || ! python -c 'from pathlib import Path; from set_data import read_env; v=read_env(Path(".env")); raise SystemExit(0 if any(v.get(k) for k in ("GEMINI_API_KEY_1","OPENAI_API_KEY","ANTHROPIC_API_KEY")) else 1)'; then
  python set_data.py
else
  if [ "${1:-}" = "--gui" ]; then python product_sorter_gui.py
  elif [ "${1:-}" = "--cli" ]; then shift; python product_sorter.py "$@"
  else
    echo "[1] GUI / واجهة رسومية"
    echo "[2] CLI / طرفية"
    read -r -p "Choose / اختر [1]: " mode
    if [ "${mode:-1}" = "2" ]; then python product_sorter.py "$@"; else python product_sorter_gui.py; fi
  fi
fi
