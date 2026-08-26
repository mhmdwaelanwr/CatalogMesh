"""Command-line entry point for the shared Product Sorter engine."""

from .core import *  # noqa: F401,F403 - intentionally preserves the public CLI API
from .core import main


if __name__ == "__main__":
    raise SystemExit(main())
