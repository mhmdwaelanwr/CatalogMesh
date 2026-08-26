"""Desktop GUI facade over the compatibility-preserved Tkinter implementation."""

from __future__ import annotations

import sys

from .paths import runtime_root
from . import setup_wizard as _setup_wizard  # ensure patched configuration paths
from . import _gui_impl as _impl

_impl.ROOT = runtime_root()


def _command(self):
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--cli-worker"]
    else:
        cmd = [sys.executable, str(_impl.ROOT / "product_sorter.py")]
    cmd += [
        "--non-interactive",
        "--source", self.vars["source"].get(),
        "--output", self.vars["output"].get(),
    ]
    if self.vars["prices"].get():
        cmd += ["--prices", self.vars["prices"].get()]
    if self.vars["sample"].get():
        cmd += ["--limit", self.vars["sample"].get()]
    return cmd


_impl.App.command = _command

globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("_")})
main = _impl.main
