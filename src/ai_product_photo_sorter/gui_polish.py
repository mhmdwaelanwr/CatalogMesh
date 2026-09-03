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


def apply_gui_polish(module: Any) -> None:
    """Add responsive scrolling, compact navigation, and theme consistency.

    Feature modules keep owning their canonical content frames. This final layer
    wraps only the workspaces that can outgrow a laptop-height viewport
    (Operation setup, Benchmark, and Review) in a vertical canvas after every
    feature has finished building. The content widgets are not recreated, so
    their callbacks and state stay untouched.
    """

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

        for info in getattr(self, "_workspace_scrolls", {}).values():
            info["canvas"].configure(bg=self.colors["panel"])

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

        # ``clam`` still falls back to platform colors for readonly combobox
        # fields unless state maps are explicit. That produced the pale grey
        # fields / low-contrast white text visible in dark-mode screenshots.
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

        # The combobox popdown list is a classic Tk Listbox on several
        # platforms, so ttk styling alone does not recolor it.
        self.root.option_add("*TCombobox*Listbox.background", self.colors["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", self.colors["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.colors["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        sync_raw_widget_colors(self)

    def _wrap_workspace(self, content, key: str):
        if content is None:
            return None
        notebook = self.main_tabs
        try:
            index = notebook.index(content)
        except module.tk.TclError:
            return None

        tab_text = notebook.tab(content, "text")
        tab_state = notebook.tab(content, "state")
        notebook.forget(content)

        host = module.ttk.Frame(notebook, style="Panel.TFrame")
        notebook.insert(index, host, text=tab_text, state=tab_state)

        canvas = module.tk.Canvas(
            host,
            bg=self.colors["panel"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = module.ttk.Scrollbar(
            host,
            orient="vertical",
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event):
            # Keep fill/expand layouts behaving like a normal notebook page,
            # but let genuinely taller content request more height and scroll.
            content.update_idletasks()
            requested_height = max(content.winfo_reqheight(), int(event.height))
            canvas.itemconfigure(
                window_id,
                width=max(1, int(event.width)),
                height=max(1, requested_height),
            )
            update_scrollregion()

        content.bind("<Configure>", update_scrollregion, add="+")
        canvas.bind("<Configure>", resize_content, add="+")
        self._workspace_scrolls[key] = {
            "host": host,
            "content": content,
            "canvas": canvas,
            "scrollbar": scrollbar,
            "window": window_id,
        }
        return host

    def _event_in_workspace(self, event_widget, info) -> bool:
        if event_widget is None:
            return False
        path = str(event_widget)
        content_path = str(info["content"])
        host_path = str(info["host"])
        canvas_path = str(info["canvas"])
        return (
            path == content_path
            or path.startswith(content_path + ".")
            or path == host_path
            or path.startswith(host_path + ".")
            or path == canvas_path
        )

    def _workspace_mousewheel(self, event):
        # Preserve native scrolling for data grids and text viewers.
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
                top, bottom = info["canvas"].yview()
                if bottom - top >= 0.999:
                    return None
                info["canvas"].yview_scroll(units, "units")
                return "break"
        return None

    def build(self):
        base_build(self)

        self._workspace_scrolls = {}

        # Operation setup is the original first tab. Wrap it after all feature
        # cards have been inserted so every existing widget scrolls together.
        tabs = self.main_tabs.tabs()
        if tabs:
            setup_content = self.main_tabs.nametowidget(tabs[0])
            self.setup_page = setup_content
            self.setup_tab = _wrap_workspace(self, setup_content, "setup")

        benchmark_content = getattr(self, "benchmark_page", None)
        if benchmark_content is not None:
            self.benchmark_tab = _wrap_workspace(
                self, benchmark_content, "benchmark"
            )

        review_content = getattr(self, "review_page", None)
        if review_content is not None:
            self.review_content_page = review_content
            review_host = _wrap_workspace(self, review_content, "review")
            if review_host is not None:
                # Review methods select/rename ``self.review_page`` later.
                self.review_page = review_host

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
        self.workspace_nav.bind(
            "<<ComboboxSelected>>", self.select_workspace_from_nav
        )
        self.main_tabs.bind(
            "<<NotebookTabChanged>>", self.sync_workspace_nav, add="+"
        )

        # Own these bindings explicitly rather than ttk.Notebook.enable_traversal()
        # so Ctrl+Tab cannot be applied twice on platforms with class bindings.
        self.root.bind(
            "<Control-Tab>", lambda event: self.cycle_workspace(1), add="+"
        )
        self.root.bind(
            "<Control-Shift-Tab>",
            lambda event: self.cycle_workspace(-1),
            add="+",
        )
        self.root.bind(
            "<Alt-w>", lambda event: self.focus_workspace_nav(), add="+"
        )
        self.root.bind(
            "<Configure>", self._responsive_workspace_nav, add="+"
        )

        # Toplevel bindings see wheel events from descendant widgets without
        # using bind_all(), so Automation Center's own local wheel guard cannot
        # accidentally remove these bindings.
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
        self.main_tabs.select(
            entries[next_tab_index(current, len(entries), step)][0]
        )
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
            self.workspace_nav_label.configure(
                text=labels.get(self.lang, "Workspace")
            )
            self.sync_workspace_nav()

    module.App.configure_styles = configure_styles
    module.App.build = build
    module.App.apply_language = apply_language
    module.App.sync_raw_widget_colors = sync_raw_widget_colors
    module.App._wrap_workspace = _wrap_workspace
    module.App._workspace_mousewheel = _workspace_mousewheel
    module.App.workspace_entries = workspace_entries
    module.App.sync_workspace_nav = sync_workspace_nav
    module.App.select_workspace_from_nav = select_workspace_from_nav
    module.App.cycle_workspace = cycle_workspace
    module.App.focus_workspace_nav = focus_workspace_nav
    module.App._responsive_workspace_nav = _responsive_workspace_nav
