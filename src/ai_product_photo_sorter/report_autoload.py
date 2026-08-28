"""Keep Report Center synchronized with configuration/output-path changes."""

from __future__ import annotations

from typing import Any


def apply_report_autoload(module: Any) -> None:
    base_load_values = module.App.load_values
    base_reload_environment = getattr(module.App, "reload_environment", None)

    def load_values(self):
        result = base_load_values(self)
        if hasattr(self, "report_tree"):
            self.refresh_reports()
        return result

    def reload_environment(self):
        result = base_reload_environment(self) if base_reload_environment else None
        if hasattr(self, "report_tree"):
            self.refresh_reports()
        return result

    module.App.load_values = load_values
    if base_reload_environment is not None:
        module.App.reload_environment = reload_environment
