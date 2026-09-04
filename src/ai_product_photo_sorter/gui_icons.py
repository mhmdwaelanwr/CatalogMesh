"""Non-invasive icon presentation layer for the CatalogMesh Tkinter GUI.

Icons are drawn into ``PhotoImage`` objects at runtime. This keeps the layer
packaging-safe for source and frozen builds while leaving widget ownership,
geometry, commands, state, localization and connector behavior untouched.
"""
from __future__ import annotations

from typing import Any

WORKSPACE_ICON_KEYS = {
    "Operation setup": "operation", "Setup": "operation",
    "Models & API keys": "models", "API": "models",
    "Results & activity": "results", "Results": "results",
    "Review": "review", "SKU Match": "sku", "Exports": "exports",
    "Storage": "storage", "Automation": "automation", "Reports": "reports",
    "Benchmark": "benchmark", "Environment": "environment", "About": "about",
}
WORKSPACE_ORDER_KEYS = (
    "operation", "models", "results", "review", "sku", "exports",
    "storage", "automation", "reports", "benchmark", "environment", "about",
)
ACTION_ICON_KEYS = {
    "start": "start", "stop": "stop", "resume": "resume",
    "save": "save", "open": "open",
}
PROVIDERS = ("GEMINI", "OPENAI", "ANTHROPIC")

# Each icon is intentionally tiny/simple so it remains crisp at native Tk scale.
# Segments are drawn on a 20x20 transparent image; rectangles/points add emphasis.
ICON_SEGMENTS = {
    "operation": (((6,4,6,16),(6,4,16,10),(6,16,16,10)), ()),
    "models": (((10,2,10,5),(10,15,10,18),(2,10,5,10),(15,10,18,10)), ((5,5,15,15),)),
    "results": (((4,15,8,10),(8,10,11,13),(11,13,16,6),(4,16,17,16)), ()),
    "review": (((7,10,9,12),(9,12,14,7)), ((4,4,16,16),)),
    "sku": (((4,7,10,3),(10,3,17,10),(17,10,10,17),(10,17,4,11),(4,11,4,7)), ()),
    "exports": (((10,3,10,12),(7,6,10,3),(10,3,13,6)), ((4,9,16,16),)),
    "storage": (((4,6,4,15),(16,6,16,15),(4,15,16,15)), ((4,3,16,7),)),
    "automation": (((11,2,5,11),(5,11,10,11),(10,11,8,18),(8,18,16,8),(16,8,11,8),(11,8,11,2)), ()),
    "reports": (((8,7,12,7),(8,11,13,11)), ((5,3,15,17),)),
    "benchmark": (((5,14,10,7),(10,7,15,14),(10,12,15,8)), ()),
    "environment": (((6,8,9,10),(9,10,6,12),(10,12,14,12)), ((3,4,17,16),)),
    "about": (((10,9,10,14),), ((3,3,17,17),(9,6,11,8))),
    "start": (((6,4,16,10),(16,10,6,16),(6,16,6,4)), ()),
    "stop": ((), ((5,5,15,15),)),
    "resume": (((5,6,8,3),(8,3,12,3),(12,3,16,7),(16,7,16,12),(16,12,12,16),(12,16,7,16),(7,16,4,13)), ()),
    "save": (((7,5,13,5),(7,12,13,12)), ((4,3,16,17),(7,11,13,16))),
    "open": (((4,7,8,4),(8,4,13,4),(13,4,15,7)), ((3,7,17,16),)),
    "theme": (((6,4,4,8),(4,8,5,13),(5,13,9,16),(9,16,14,15)), ()),
    "refresh": (((5,7,8,4),(8,4,13,4),(13,4,16,7),(16,7,16,12),(16,12,13,15),(13,15,8,16)), ()),
}


def _line_points(x0: int, y0: int, x1: int, y1: int):
    dx, dy = abs(x1-x0), -abs(y1-y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy


def _plot(image, x: int, y: int, color: str, thickness: int = 2) -> None:
    for ox in range(-(thickness//2), thickness-(thickness//2)):
        for oy in range(-(thickness//2), thickness-(thickness//2)):
            px, py = x + ox, y + oy
            if 0 <= px < 20 and 0 <= py < 20:
                image.put(color, (px, py))


def _draw_rect(image, rect, color: str, fill: bool = False) -> None:
    x0, y0, x1, y1 = rect
    if fill:
        image.put(color, to=(x0, y0, x1 + 1, y1 + 1))
        return
    for x in range(x0, x1 + 1):
        _plot(image, x, y0, color, 1); _plot(image, x, y1, color, 1)
    for y in range(y0, y1 + 1):
        _plot(image, x0, y, color, 1); _plot(image, x1, y, color, 1)


def _make_icon(module: Any, key: str, color: str):
    image = module.tk.PhotoImage(width=20, height=20)
    lines, rects = ICON_SEGMENTS.get(key, ((), ()))
    for segment in lines:
        for x, y in _line_points(*segment):
            _plot(image, x, y, color)
    for rect in rects:
        _draw_rect(image, rect, color, fill=(key in {"stop"} or rect in {(9,6,11,8)}))
    return image


def _make_provider_icon(module: Any, provider: str):
    colors = {"GEMINI": "#4285f4", "OPENAI": "#10a37f", "ANTHROPIC": "#cc795c"}
    color = colors[provider]
    image = module.tk.PhotoImage(width=20, height=20)
    if provider == "GEMINI":
        paths = ((10,2,17,10),(17,10,10,18),(10,18,3,10),(3,10,10,2))
    elif provider == "OPENAI":
        paths = ((10,3,15,6),(15,6,16,12),(16,12,11,17),(11,17,5,14),(5,14,4,8),(4,8,10,3),(7,7,13,13),(13,7,7,13))
    else:
        paths = ((4,17,10,3),(10,3,16,17),(7,12,13,12))
    for segment in paths:
        for x, y in _line_points(*segment):
            _plot(image, x, y, color)
    return image


def _photo(module: Any, owner: Any, key: str, provider: bool = False):
    cache = getattr(owner, "_catalogmesh_icon_cache", None)
    if cache is None:
        cache = {}; owner._catalogmesh_icon_cache = cache
    cache_key = ("provider" if provider else "icon", key, getattr(owner, "theme", "dark"))
    if cache_key in cache:
        return cache[cache_key]
    try:
        color = getattr(owner, "colors", {}).get("muted", "#94a3b8")
        image = _make_provider_icon(module, key) if provider else _make_icon(module, key, color)
    except module.tk.TclError:
        return None
    cache[cache_key] = image
    return image


def _workspace_icon_key(label: str) -> str | None:
    logical = str(label or "").strip()
    direct = WORKSPACE_ICON_KEYS.get(logical)
    if direct:
        return direct
    folded = logical.casefold()
    return next((key for known, key in WORKSPACE_ICON_KEYS.items() if known.casefold() == folded), None)


def _decorate_sidebar(self, module: Any) -> None:
    entries = list(self.workspace_entries()) if hasattr(self, "workspace_entries") else []
    positional = len(entries) == len(WORKSPACE_ORDER_KEYS)
    for index, (tab_id, label) in enumerate(entries):
        button = getattr(self, "sidebar_buttons", {}).get(str(tab_id))
        if button is None:
            continue
        key = _workspace_icon_key(label) or (WORKSPACE_ORDER_KEYS[index] if positional else None)
        image = _photo(module, self, key) if key else None
        try:
            button.configure(image=image or "", compound="left")
        except module.tk.TclError:
            pass


def _decorate_actions(self, module: Any) -> None:
    for name, icon_key in ACTION_ICON_KEYS.items():
        button = getattr(self, "buttons", {}).get(name)
        if button is not None:
            try:
                button.configure(image=_photo(module, self, icon_key) or "", compound="left")
            except module.tk.TclError:
                pass
    theme = getattr(self, "theme_button", None)
    if theme is not None:
        try:
            theme.configure(image=_photo(module, self, "theme") or "", compound="left")
        except module.tk.TclError:
            pass


def _decorate_provider_tabs(self, module: Any) -> None:
    root = getattr(self, "main_tabs", None)
    if root is None:
        return
    stack = list(root.winfo_children())
    while stack:
        widget = stack.pop()
        try:
            stack.extend(widget.winfo_children())
        except module.tk.TclError:
            pass
        if not isinstance(widget, module.ttk.Notebook):
            continue
        for tab_id in widget.tabs():
            try:
                label = str(widget.tab(tab_id, "text") or "").strip().upper()
            except module.tk.TclError:
                continue
            if label in PROVIDERS:
                try:
                    widget.tab(tab_id, image=_photo(module, self, label, provider=True) or "", compound="left")
                except module.tk.TclError:
                    pass


def _decorate_refresh_buttons(self, module: Any) -> None:
    image = _photo(module, self, "refresh")
    for provider in PROVIDERS:
        button = getattr(self, provider + "_refresh_button", None)
        if button is not None:
            try:
                button.configure(image=image or "", compound="left")
            except module.tk.TclError:
                pass


def apply_gui_icons(module: Any) -> None:
    """Install icons as a final, fail-safe presentation layer."""
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_configure_styles = module.App.configure_styles
    base_rebuild_sidebar = getattr(module.App, "rebuild_workspace_sidebar", None)
    base_sync_sidebar = getattr(module.App, "sync_workspace_sidebar", None)

    def decorate(self):
        _decorate_sidebar(self, module); _decorate_actions(self, module)
        _decorate_provider_tabs(self, module); _decorate_refresh_buttons(self, module)

    def build(self):
        base_build(self); decorate(self)

    def apply_language(self):
        base_apply_language(self); decorate(self)

    def configure_styles(self):
        base_configure_styles(self)
        # Recreate theme-aware monochrome icons after a theme switch.
        self._catalogmesh_icon_cache = {}
        if hasattr(self, "main_tabs"):
            decorate(self)

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.configure_styles = configure_styles
    module.App.decorate_catalogmesh_icons = decorate

    if base_rebuild_sidebar is not None:
        def rebuild_workspace_sidebar(self):
            base_rebuild_sidebar(self); _decorate_sidebar(self, module)
        module.App.rebuild_workspace_sidebar = rebuild_workspace_sidebar

    if base_sync_sidebar is not None:
        def sync_workspace_sidebar(self, event=None):
            base_sync_sidebar(self, event); _decorate_sidebar(self, module)
        module.App.sync_workspace_sidebar = sync_workspace_sidebar
