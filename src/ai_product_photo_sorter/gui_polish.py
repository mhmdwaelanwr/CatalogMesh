"""Final desktop layout polish applied after all feature workspaces are installed."""
from __future__ import annotations

from typing import Any


SCROLLABLE_WORKSPACE_KEYS = ("setup", "benchmark", "review")


def next_tab_index(current: int, count: int, step: int = 1) -> int:
    """Return a wrapped notebook index for keyboard workspace navigation."""
    if count <= 0:
        return 0
    return (current + step) % count


def wheel_units(delta: int = 0, button: int | None = None) -> int:
    """Normalize Windows/macOS wheel deltas and Linux Button-4/5 events."""
    if button == 4:
        return -3
    if button == 5:
        return 3
    if not delta:
        return 0
    magnitude = max(1, min(4, abs(int(delta)) // 120 or 1))
    return -magnitude if delta > 0 else magnitude


def clamp_scroll_offset(offset: int, total: int, viewport: int) -> int:
    """Clamp a packed-workspace scroll offset to its valid range."""
    maximum = max(0, int(total) - max(1, int(viewport)))
    return max(0, min(int(offset), maximum))


def _as_int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _pair(value) -> tuple[int, int]:
    if isinstance(value, (tuple, list)):
        if not value:
            return (0, 0)
        if len(value) == 1:
            number = _as_int(value[0])
            return (number, number)
        return (_as_int(value[0]), _as_int(value[1]))
    text = str(value or "").replace("{", " ").replace("}", " ").replace(",", " ")
    parts = [part for part in text.split() if part]
    if not parts:
        return (0, 0)
    if len(parts) == 1:
        number = _as_int(parts[0])
        return (number, number)
    return (_as_int(parts[0]), _as_int(parts[1]))


def _frame_padding(widget) -> tuple[int, int, int, int]:
    try:
        raw = widget.cget("padding")
    except Exception:
        return (0, 0, 0, 0)
    if isinstance(raw, (tuple, list)):
        parts = [_as_int(item) for item in raw]
    else:
        text = str(raw or "").replace("{", " ").replace("}", " ").replace(",", " ")
        parts = [_as_int(item) for item in text.split() if item]
    if not parts:
        return (0, 0, 0, 0)
    if len(parts) == 1:
        return (parts[0], parts[0], parts[0], parts[0])
    if len(parts) == 2:
        return (parts[0], parts[1], parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], parts[1])
    return (parts[0], parts[1], parts[2], parts[3])


class _PackedWorkspaceScroller:
    """Scroll a notebook page without re-parenting any existing Tk widgets.

    Tk widgets cannot be safely re-parented after creation. The previous GUI
    polish attempted to place an already-created notebook page inside a Canvas,
    which produced blank pages on real Tk renderers. This scroller keeps every
    widget under its original parent and only swaps the page's direct children
    from ``pack`` to ``place`` so they can be translated vertically.
    """

    def __init__(self, module: Any, owner: Any, page: Any, key: str):
        self.module = module
        self.owner = owner
        self.page = page
        self.key = key
        self.offset = 0
        self.total_height = 0
        self.viewport_height = 1
        self._layout_scheduled = False
        self._specs: list[dict[str, Any]] = []

        page.update_idletasks()
        for child in list(page.pack_slaves()):
            try:
                info = child.pack_info()
            except module.tk.TclError:
                continue
            if str(info.get("side", "top")) not in {"top", ""}:
                continue
            self._specs.append({"widget": child, "pack": dict(info)})

        if not self._specs:
            raise ValueError(f"workspace {key!r} has no packed children to scroll")

        for spec in self._specs:
            spec["widget"].pack_forget()

        self.scrollbar = module.ttk.Scrollbar(page, orient="vertical", command=self.yview)
        page.bind("<Configure>", self._schedule_layout, add="+")
        for spec in self._specs:
            spec["widget"].bind("<Configure>", self._schedule_layout, add="+")
        page.after_idle(self.relayout)

    def _schedule_layout(self, _event=None):
        if self._layout_scheduled:
            return
        self._layout_scheduled = True
        self.page.after_idle(self._run_scheduled_layout)

    def _run_scheduled_layout(self):
        self._layout_scheduled = False
        try:
            self.relayout()
        except self.module.tk.TclError:
            pass

    def _natural_layout(self, available_width: int):
        items: list[dict[str, Any]] = []
        natural_total = 0
        expand_indexes: list[int] = []
        for index, spec in enumerate(self._specs):
            child = spec["widget"]
            info = spec["pack"]
            pad_left, pad_right = _pair(info.get("padx", 0))
            pad_top, pad_bottom = _pair(info.get("pady", 0))
            ipadx = _as_int(info.get("ipadx", 0))
            ipady = _as_int(info.get("ipady", 0))
            fill = str(info.get("fill", "none"))
            anchor = str(info.get("anchor", "center"))
            expand = str(info.get("expand", "0")).lower() in {"1", "true", "yes"}
            requested_height = max(1, int(child.winfo_reqheight()) + 2 * ipady)
            requested_width = max(1, int(child.winfo_reqwidth()) + 2 * ipadx)
            width = (
                max(1, available_width - pad_left - pad_right)
                if fill in {"x", "both"}
                else min(requested_width, max(1, available_width - pad_left - pad_right))
            )
            item = {
                "widget": child,
                "pad_left": pad_left,
                "pad_right": pad_right,
                "pad_top": pad_top,
                "pad_bottom": pad_bottom,
                "height": requested_height,
                "width": width,
                "anchor": anchor,
            }
            items.append(item)
            natural_total += pad_top + requested_height + pad_bottom
            if expand:
                expand_indexes.append(index)
        return items, natural_total, expand_indexes

    def relayout(self):
        self.page.update_idletasks()
        width = max(1, int(self.page.winfo_width()))
        height = max(1, int(self.page.winfo_height()))
        left, top, right, bottom = _frame_padding(self.page)
        scrollbar_width = max(14, int(self.scrollbar.winfo_reqwidth()))
        gutter = scrollbar_width + 5
        available_width = max(1, width - left - right - gutter)
        available_height = max(1, height - top - bottom)

        items, children_height, expand_indexes = self._natural_layout(available_width)
        natural_total = top + children_height + bottom
        if natural_total < height and expand_indexes:
            extra = height - natural_total
            each, remainder = divmod(extra, len(expand_indexes))
            for order, index in enumerate(expand_indexes):
                items[index]["height"] += each + (1 if order < remainder else 0)

        self.total_height = top + bottom + sum(
            item["pad_top"] + item["height"] + item["pad_bottom"] for item in items
        )
        self.viewport_height = height
        self.offset = clamp_scroll_offset(self.offset, self.total_height, self.viewport_height)

        y = top - self.offset
        for item in items:
            y += item["pad_top"]
            child = item["widget"]
            anchor = item["anchor"]
            if "w" in anchor:
                x = left + item["pad_left"]
            elif "e" in anchor:
                x = width - right - gutter - item["pad_right"] - item["width"]
            else:
                usable = max(1, available_width - item["pad_left"] - item["pad_right"])
                x = left + item["pad_left"] + max(0, (usable - item["width"]) // 2)
            child.place(
                x=max(0, int(x)),
                y=int(y),
                width=max(1, int(item["width"])),
                height=max(1, int(item["height"])),
            )
            y += item["height"] + item["pad_bottom"]

        if self.total_height > self.viewport_height + 1:
            self.scrollbar.place(
                x=max(0, width - right - scrollbar_width),
                y=max(0, top),
                width=scrollbar_width,
                height=available_height,
            )
            first = self.offset / max(1, self.total_height)
            last = min(1.0, (self.offset + self.viewport_height) / max(1, self.total_height))
            self.scrollbar.set(first, last)
        else:
            self.scrollbar.place_forget()
            self.scrollbar.set(0.0, 1.0)

    def can_scroll(self) -> bool:
        return self.total_height > self.viewport_height + 1

    def scroll_units(self, units: int):
        if not units or not self.can_scroll():
            return
        self.offset = clamp_scroll_offset(
            self.offset + int(units) * 42,
            self.total_height,
            self.viewport_height,
        )
        self.relayout()

    def yview(self, *args):
        if not args:
            if self.total_height <= 0:
                return (0.0, 1.0)
            return (
                self.offset / self.total_height,
                min(1.0, (self.offset + self.viewport_height) / self.total_height),
            )
        command = str(args[0])
        if command == "moveto" and len(args) >= 2:
            fraction = max(0.0, min(1.0, float(args[1])))
            maximum = max(0, self.total_height - self.viewport_height)
            self.offset = int(round(maximum * fraction))
        elif command == "scroll" and len(args) >= 3:
            amount = int(args[1])
            kind = str(args[2])
            step = max(40, int(self.viewport_height * 0.85)) if kind == "pages" else 42
            self.offset = clamp_scroll_offset(
                self.offset + amount * step,
                self.total_height,
                self.viewport_height,
            )
        self.relayout()


def apply_gui_polish(module: Any) -> None:
    """Add safe page scrolling, compact navigation, and theme consistency."""

    base_configure_styles = module.App.configure_styles
    base_build = module.App.build
    base_apply_language = module.App.apply_language

    def sync_raw_widget_colors(self):
        """Theme raw Tk surfaces that ttk styles do not cover."""
        if hasattr(self, "automation_canvas"):
            self.automation_canvas.configure(bg=self.colors["panel"])
        for name in ("automation_preview", "automation_output"):
            widget = getattr(self, name, None)
            if widget is None:
                continue
            widget.configure(
                bg=self.colors["panel2"],
                fg=self.colors["text"],
                insertbackground=self.colors["text"],
                selectbackground=self.colors["accent"],
                selectforeground="#ffffff",
                relief="flat",
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=self.colors["border"],
                highlightcolor=self.colors["accent"],
            )

    def configure_styles(self):
        base_configure_styles(self)
        style = module.ttk.Style(self.root)
        style.configure(
            "TNotebook.Tab",
            background=self.colors["panel2"],
            foreground=self.colors["muted"],
            padding=(10, 7),
            font=("Sans", 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["accent"])],
            foreground=[("selected", "#fff")],
        )
        style.configure(
            "Workspace.TLabel",
            background=self.colors["bg"],
            foreground=self.colors["muted"],
            font=("Sans", 9, "bold"),
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.colors["field"],
            background=self.colors["field"],
            foreground=self.colors["text"],
            arrowcolor=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground="#ffffff",
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("disabled", self.colors["panel2"]),
                ("readonly", self.colors["field"]),
            ],
            background=[
                ("disabled", self.colors["panel2"]),
                ("readonly", self.colors["field"]),
                ("active", self.colors["panel2"]),
            ],
            foreground=[
                ("disabled", self.colors["muted"]),
                ("readonly", self.colors["text"]),
            ],
            arrowcolor=[
                ("disabled", self.colors["muted"]),
                ("readonly", self.colors["text"]),
            ],
            selectbackground=[("readonly", self.colors["accent"])],
            selectforeground=[("readonly", "#ffffff")],
        )
        style.configure(
            "TEntry",
            fieldbackground=self.colors["field"],
            foreground=self.colors["text"],
            insertcolor=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground="#ffffff",
        )
        self.root.option_add("*TCombobox*Listbox.background", self.colors["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", self.colors["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.colors["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        sync_raw_widget_colors(self)

    def _install_workspace_scroller(self, page, key: str):
        if page is None:
            return None
        try:
            scroller = _PackedWorkspaceScroller(module, self, page, key)
        except (ValueError, module.tk.TclError):
            return None
        self._workspace_scrolls[key] = {
            "page": page,
            "content": page,
            "host": page,
            "scrollbar": scroller.scrollbar,
            "scroller": scroller,
        }
        return scroller

    def _event_in_workspace(self, event_widget, info) -> bool:
        if event_widget is None:
            return False
        path = str(event_widget)
        page_path = str(info["page"])
        return path == page_path or path.startswith(page_path + ".")

    def _workspace_mousewheel(self, event):
        if isinstance(event.widget, (module.ttk.Treeview, module.tk.Text)):
            return None
        units = wheel_units(
            int(getattr(event, "delta", 0) or 0),
            getattr(event, "num", None),
        )
        if not units:
            return None
        for info in getattr(self, "_workspace_scrolls", {}).values():
            if _event_in_workspace(self, event.widget, info):
                scroller = info["scroller"]
                if not scroller.can_scroll():
                    return None
                scroller.scroll_units(units)
                return "break"
        return None

    def build(self):
        base_build(self)
        self._workspace_scrolls = {}

        tabs = self.main_tabs.tabs()
        if tabs:
            self.setup_page = self.main_tabs.nametowidget(tabs[0])
            self.setup_scroller = _install_workspace_scroller(self, self.setup_page, "setup")

        benchmark_page = getattr(self, "benchmark_page", None)
        if benchmark_page is not None:
            self.benchmark_scroller = _install_workspace_scroller(
                self, benchmark_page, "benchmark"
            )

        review_page = getattr(self, "review_page", None)
        if review_page is not None:
            self.review_scroller = _install_workspace_scroller(self, review_page, "review")

        self.workspace_nav_frame = module.ttk.Frame(self.header, style="App.TFrame")
        self.workspace_nav_frame.pack(side="right", padx=(0, 8), pady=8)
        self.workspace_nav_label = module.ttk.Label(
            self.workspace_nav_frame,
            text="Workspace",
            style="Workspace.TLabel",
        )
        self.workspace_nav_label.pack(side="left", padx=(0, 6))
        self.workspace_nav_value = module.tk.StringVar(value="")
        self.workspace_nav = module.ttk.Combobox(
            self.workspace_nav_frame,
            textvariable=self.workspace_nav_value,
            state="readonly",
            width=24,
        )
        self.workspace_nav.pack(side="left")
        self.workspace_nav.bind("<<ComboboxSelected>>", self.select_workspace_from_nav)
        self.main_tabs.bind("<<NotebookTabChanged>>", self.sync_workspace_nav, add="+")

        self.root.bind("<Control-Tab>", lambda event: self.cycle_workspace(1), add="+")
        self.root.bind(
            "<Control-Shift-Tab>",
            lambda event: self.cycle_workspace(-1),
            add="+",
        )
        self.root.bind("<Alt-w>", lambda event: self.focus_workspace_nav(), add="+")
        self.root.bind("<Configure>", self._responsive_workspace_nav, add="+")
        self.root.bind("<MouseWheel>", self._workspace_mousewheel, add="+")
        self.root.bind("<Button-4>", self._workspace_mousewheel, add="+")
        self.root.bind("<Button-5>", self._workspace_mousewheel, add="+")

        self.sync_workspace_nav()
        sync_raw_widget_colors(self)

    def workspace_entries(self):
        entries = []
        for tab_id in self.main_tabs.tabs():
            text = str(self.main_tabs.tab(tab_id, "text") or "").strip()
            entries.append((tab_id, text or "Workspace"))
        return entries

    def sync_workspace_nav(self, _event=None):
        if not hasattr(self, "workspace_nav"):
            return
        entries = self.workspace_entries()
        labels = [label for _tab_id, label in entries]
        self.workspace_nav.configure(values=labels)
        selected = self.main_tabs.select()
        for tab_id, label in entries:
            if str(tab_id) == str(selected):
                self.workspace_nav_value.set(label)
                break

    def select_workspace_from_nav(self, _event=None):
        wanted = self.workspace_nav_value.get()
        for tab_id, label in self.workspace_entries():
            if label == wanted:
                self.main_tabs.select(tab_id)
                self.main_tabs.focus_set()
                return

    def cycle_workspace(self, step: int):
        entries = self.workspace_entries()
        if not entries:
            return "break"
        selected = str(self.main_tabs.select())
        current = next(
            (
                index
                for index, (tab_id, _label) in enumerate(entries)
                if str(tab_id) == selected
            ),
            0,
        )
        self.main_tabs.select(entries[next_tab_index(current, len(entries), step)][0])
        return "break"

    def focus_workspace_nav(self):
        self.workspace_nav.focus_set()
        return "break"

    def _responsive_workspace_nav(self, event=None):
        if (
            not hasattr(self, "workspace_nav")
            or event is None
            or event.widget is not self.root
        ):
            return
        width = int(event.width)
        if width < 1080:
            self.workspace_nav_label.pack_forget()
            self.workspace_nav.configure(width=18)
        else:
            if not self.workspace_nav_label.winfo_manager():
                self.workspace_nav_label.pack(
                    side="left", padx=(0, 6), before=self.workspace_nav
                )
            self.workspace_nav.configure(width=24 if width < 1320 else 28)

    def apply_language(self):
        base_apply_language(self)
        if hasattr(self, "workspace_nav_label"):
            labels = {"ar": "مساحة العمل", "en": "Workspace", "zh": "工作区"}
            self.workspace_nav_label.configure(text=labels.get(self.lang, "Workspace"))
            self.sync_workspace_nav()

    module.App.configure_styles = configure_styles
    module.App.build = build
    module.App.apply_language = apply_language
    module.App.sync_raw_widget_colors = sync_raw_widget_colors
    module.App._install_workspace_scroller = _install_workspace_scroller
    module.App._workspace_mousewheel = _workspace_mousewheel
    module.App.workspace_entries = workspace_entries
    module.App.sync_workspace_nav = sync_workspace_nav
    module.App.select_workspace_from_nav = select_workspace_from_nav
    module.App.cycle_workspace = cycle_workspace
    module.App.focus_workspace_nav = focus_workspace_nav
    module.App._responsive_workspace_nav = _responsive_workspace_nav
