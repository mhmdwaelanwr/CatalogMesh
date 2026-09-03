"""Final desktop layout polish applied after all feature workspaces are installed."""
from __future__ import annotations

from typing import Any


def next_tab_index(current: int, count: int, step: int = 1) -> int:
    """Return a wrapped notebook index for keyboard workspace navigation."""
    if count <= 0:
        return 0
    return (current + step) % count


def apply_gui_polish(module: Any) -> None:
    """Add compact, accessible navigation without changing workspace ownership.

    Feature modules keep using the canonical ``main_tabs`` notebook. The final
    polish layer adds a workspace picker and keyboard navigation so a growing
    number of tabs stays reachable on smaller displays.
    """

    base_configure_styles = module.App.configure_styles
    base_build = module.App.build
    base_apply_language = module.App.apply_language

    def sync_raw_widget_colors(self):
        """Theme the non-ttk scrolling/text surfaces created by feature modules."""
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
        sync_raw_widget_colors(self)

    def build(self):
        base_build(self)
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

        # Own these bindings explicitly rather than ttk.Notebook.enable_traversal()
        # so Ctrl+Tab cannot be applied twice on platforms with class bindings.
        self.root.bind("<Control-Tab>", lambda event: self.cycle_workspace(1), add="+")
        self.root.bind("<Control-Shift-Tab>", lambda event: self.cycle_workspace(-1), add="+")
        self.root.bind("<Alt-w>", lambda event: self.focus_workspace_nav(), add="+")
        self.root.bind("<Configure>", self._responsive_workspace_nav, add="+")
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
            (index for index, (tab_id, _label) in enumerate(entries) if str(tab_id) == selected),
            0,
        )
        self.main_tabs.select(entries[next_tab_index(current, len(entries), step)][0])
        return "break"

    def focus_workspace_nav(self):
        self.workspace_nav.focus_set()
        return "break"

    def _responsive_workspace_nav(self, event=None):
        if not hasattr(self, "workspace_nav") or event is None or event.widget is not self.root:
            return
        width = int(event.width)
        if width < 1080:
            self.workspace_nav_label.pack_forget()
            self.workspace_nav.configure(width=18)
        else:
            if not self.workspace_nav_label.winfo_manager():
                self.workspace_nav_label.pack(side="left", padx=(0, 6), before=self.workspace_nav)
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
    module.App.workspace_entries = workspace_entries
    module.App.sync_workspace_nav = sync_workspace_nav
    module.App.select_workspace_from_nav = select_workspace_from_nav
    module.App.cycle_workspace = cycle_workspace
    module.App.focus_workspace_nav = focus_workspace_nav
    module.App._responsive_workspace_nav = _responsive_workspace_nav
