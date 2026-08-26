#!/usr/bin/env python3
"""Compatibility launcher for the organized live API smoke test."""

from scripts.smoke.live_api_smoke import main


if __name__ == "__main__":
    raise SystemExit(main())
