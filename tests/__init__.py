"""Test bootstrap for source checkouts that have not been installed editable yet."""

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
