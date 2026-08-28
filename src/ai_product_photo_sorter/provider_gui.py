"""Desktop preflight for canonical provider configuration."""

from __future__ import annotations

from typing import Any

from .provider_selection import ProviderSelectionError, canonical_provider_string


def apply_provider_gui(module: Any) -> None:
    base_start = module.App.start

    def start(self):
        raw = self.vars.get("providers").get() if "providers" in self.vars else "gemini"
        try:
            canonical, corrections = canonical_provider_string(raw)
        except ProviderSelectionError as exc:
            module.messagebox.showerror("Provider configuration", str(exc))
            self.status.set("Provider configuration needs attention")
            return None

        if "providers" in self.vars:
            self.vars["providers"].set(canonical)
        if corrections:
            correction_text = ", ".join(f"{old} → {new}" for old, new in corrections)
            self.status.set(f"Provider corrected: {correction_text}")
            module.messagebox.showinfo(
                "Provider configuration",
                f"Provider priority was corrected automatically: {correction_text}",
            )
        return base_start(self)

    module.App.start = start
