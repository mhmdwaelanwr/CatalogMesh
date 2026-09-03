"""Tkinter Automation Center backed by the canonical automation CLI parser.

The GUI deliberately reuses :mod:`automation_cli` instead of duplicating remote
execution logic. Approval, reservation, connector binding, idempotency and drift
checks therefore remain identical in CLI and GUI workflows.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import shlex
import threading
from pathlib import Path
from typing import Any

from . import automation_cli

REMOTE_MUTATION_COMMANDS = frozenset(
    {
        "execute-shopify-stage",
        "execute-shopify-publish",
        "execute-shopify-rollback",
        "execute-akeneo-products",
        "execute-akeneo-rollback",
        "execute-odoo-products",
    }
)

_DIRECTORY_NAMES = {"root", "shoot", "state_dir", "output"}


def command_parsers() -> dict[str, argparse.ArgumentParser]:
    """Return every canonical automation CLI subcommand parser."""
    parser = automation_cli.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def command_names() -> tuple[str, ...]:
    return tuple(command_parsers())


def parser_actions(command: str) -> list[argparse.Action]:
    parser = command_parsers().get(command)
    if parser is None:
        raise ValueError(f"Unknown automation command: {command}")
    return [action for action in parser._actions if action.dest != "help"]


def _is_bool_action(action: argparse.Action) -> bool:
    return isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction))


def _is_append_action(action: argparse.Action) -> bool:
    return isinstance(action, argparse._AppendAction)


def build_argv(command: str, values: dict[str, Any]) -> list[str]:
    """Build CLI argv from GUI field values using the canonical parser metadata."""
    argv = [command]
    for action in parser_actions(command):
        value = values.get(action.dest)
        positional = not action.option_strings
        if _is_bool_action(action):
            enabled = bool(value)
            if enabled and action.option_strings:
                argv.append(action.option_strings[0])
            continue
        if value is None:
            value = ""
        text = str(value).strip()
        if positional:
            if not text:
                if action.required:
                    raise ValueError(f"Required field is missing: {action.dest}")
                continue
            argv.append(text)
            continue
        if not text:
            continue
        option = action.option_strings[0]
        if _is_append_action(action):
            entries = [part.strip() for part in text.replace("\n", ",").split(",") if part.strip()]
            for entry in entries:
                argv.extend([option, entry])
        else:
            argv.extend([option, text])
    # Let argparse remain the final authority on shape/types/choices.
    automation_cli.build_parser().parse_args(argv)
    return argv


def cli_preview(argv: list[str]) -> str:
    return "product-sorter-automation " + " ".join(shlex.quote(part) for part in argv)


def apply_automation_gui(module: Any) -> None:
    base_build = module.App.build
    base_apply_language = module.App.apply_language
    base_set_running = module.App.set_running

    def build(self):
        base_build(self)
        self._automation_running = False
        self.automation_command = module.tk.StringVar(value=command_names()[0] if command_names() else "")
        self.automation_status = module.tk.StringVar(value="Ready")
        self.automation_confirm = module.tk.StringVar(value="")
        self.automation_field_vars: dict[str, Any] = {}
        self.automation_field_widgets: list[Any] = []

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=18)
        self.main_tabs.add(page, text="Automation")
        self.automation_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        header.pack(fill="x")
        self.automation_title = module.ttk.Label(header, text="Automation Center", style="Metric.TLabel")
        self.automation_title.pack(anchor="w")
        self.automation_hint = module.ttk.Label(
            header,
            text=(
                "GUI/CLI parity is generated from the same parser. Remote writes still require the exact "
                "approval + single-use reservation workflow; this screen never bypasses those checks."
            ),
            style="MetricName.TLabel",
            wraplength=1050,
        )
        self.automation_hint.pack(anchor="w", pady=(5, 12))

        selector = module.ttk.Frame(header, style="Card.TFrame")
        selector.pack(fill="x")
        self.automation_command_label = module.ttk.Label(selector, text="Command", style="MetricName.TLabel")
        self.automation_command_label.pack(side="left", padx=(0, 8))
        self.automation_command_box = module.ttk.Combobox(
            selector,
            textvariable=self.automation_command,
            values=command_names(),
            state="readonly",
            width=34,
        )
        self.automation_command_box.pack(side="left", padx=(0, 10))
        self.automation_command_box.bind("<<ComboboxSelected>>", lambda _event: self.rebuild_automation_form())

        self.automation_form = module.ttk.Frame(page, style="Card.TFrame", padding=18)
        self.automation_form.pack(fill="x", pady=(12, 0))

        guard = module.ttk.Frame(page, style="Card.TFrame", padding=16)
        guard.pack(fill="x", pady=(12, 0))
        self.automation_guard_label = module.ttk.Label(
            guard,
            style="MetricName.TLabel",
            wraplength=1050,
            text="Remote mutation commands require an extra GUI confirmation in addition to their approval artifacts.",
        )
        self.automation_guard_label.pack(anchor="w")
        confirm_row = module.ttk.Frame(guard, style="Card.TFrame")
        confirm_row.pack(fill="x", pady=(8, 0))
        self.automation_confirm_label = module.ttk.Label(confirm_row, text="Confirmation", style="MetricName.TLabel", width=18)
        self.automation_confirm_label.pack(side="left")
        self.automation_confirm_entry = module.ttk.Entry(confirm_row, textvariable=self.automation_confirm)
        self.automation_confirm_entry.pack(side="left", fill="x", expand=True)

        actions = module.ttk.Frame(page, style="Card.TFrame", padding=16)
        actions.pack(fill="x", pady=(12, 0))
        self.automation_run_button = module.ttk.Button(actions, text="Run", style="Accent.TButton", command=self.run_automation_command)
        self.automation_run_button.pack(side="left", padx=(0, 8))
        self.automation_clear_button = module.ttk.Button(actions, text="Clear output", style="Soft.TButton", command=self.clear_automation_output)
        self.automation_clear_button.pack(side="left")
        module.ttk.Label(actions, textvariable=self.automation_status, style="MetricName.TLabel").pack(side="right")

        preview_card = module.ttk.Frame(page, style="Card.TFrame", padding=14)
        preview_card.pack(fill="both", expand=True, pady=(12, 0))
        self.automation_preview = module.tk.Text(preview_card, height=3, wrap="word")
        self.automation_preview.pack(fill="x", pady=(0, 8))
        self.automation_output = module.tk.Text(preview_card, height=10, wrap="word")
        self.automation_output.pack(fill="both", expand=True)
        self.rebuild_automation_form()

    def _browse_for_action(self, action):
        directory = action.dest in _DIRECTORY_NAMES and action.dest not in {"output"} \
            or (action.dest == "output" and self.automation_command.get() not in {"request-external-action"})
        if directory:
            selected = module.filedialog.askdirectory(title=f"Select {action.dest}")
        else:
            selected = module.filedialog.askopenfilename(title=f"Select {action.dest}")
        if selected:
            self.automation_field_vars[action.dest].set(selected)
            self.refresh_automation_preview()

    def rebuild_automation_form(self):
        for widget in self.automation_form.winfo_children():
            widget.destroy()
        self.automation_field_vars = {}
        command = self.automation_command.get()
        self.automation_confirm.set("")
        for row_index, action in enumerate(parser_actions(command)):
            label_text = action.dest.replace("_", " ").title()
            if not action.option_strings:
                label_text += " *"
            module.ttk.Label(self.automation_form, text=label_text, style="MetricName.TLabel", width=24).grid(
                row=row_index, column=0, sticky="w", padx=(0, 8), pady=4
            )
            if _is_bool_action(action):
                variable = module.tk.BooleanVar(value=bool(action.default))
                widget = module.ttk.Checkbutton(self.automation_form, variable=variable)
                widget.grid(row=row_index, column=1, sticky="w", pady=4)
                variable.trace_add("write", lambda *_: self.refresh_automation_preview())
            else:
                default = "" if action.default in (None, argparse.SUPPRESS) else str(action.default)
                variable = module.tk.StringVar(value=default)
                if action.choices:
                    widget = module.ttk.Combobox(
                        self.automation_form,
                        textvariable=variable,
                        values=[str(value) for value in action.choices],
                        state="readonly",
                    )
                else:
                    widget = module.ttk.Entry(self.automation_form, textvariable=variable)
                widget.grid(row=row_index, column=1, sticky="ew", pady=4)
                variable.trace_add("write", lambda *_: self.refresh_automation_preview())
                if action.type is Path:
                    module.ttk.Button(
                        self.automation_form,
                        text="Browse",
                        style="Soft.TButton",
                        command=lambda current=action: _browse_for_action(self, current),
                    ).grid(row=row_index, column=2, padx=(8, 0), pady=4)
            self.automation_field_vars[action.dest] = variable
        self.automation_form.columnconfigure(1, weight=1)
        self.refresh_automation_preview()

    def automation_values(self):
        return {key: variable.get() for key, variable in self.automation_field_vars.items()}

    def refresh_automation_preview(self):
        if not hasattr(self, "automation_preview"):
            return
        self.automation_preview.delete("1.0", "end")
        try:
            argv = build_argv(self.automation_command.get(), self.automation_values())
            text = cli_preview(argv)
        except Exception as exc:
            text = f"Command preview: {exc}"
        self.automation_preview.insert("1.0", text)
        command = self.automation_command.get()
        required = f"RUN {command}" if command in REMOTE_MUTATION_COMMANDS else "Not required for this command"
        self.automation_guard_label.config(
            text=(
                "Remote mutation safety is unchanged: approval + reservation are still mandatory. "
                f"GUI confirmation for this command: {required}."
            )
        )
        self.automation_confirm_entry.config(state="normal" if command in REMOTE_MUTATION_COMMANDS else "disabled")

    def clear_automation_output(self):
        self.automation_output.delete("1.0", "end")
        self.automation_status.set("Ready")

    def _finish_automation(self, output: str, error: str | None):
        self._automation_running = False
        self.automation_output.insert("end", output or "(no output)\n")
        if error:
            self.automation_output.insert("end", f"\nERROR: {error}\n")
            self.automation_status.set("Failed")
        else:
            self.automation_status.set("Completed")
        self.automation_run_button.config(state="normal")

    def run_automation_command(self):
        if self._automation_running:
            return
        command = self.automation_command.get()
        try:
            argv = build_argv(command, self.automation_values())
        except Exception as exc:
            module.messagebox.showerror("Automation", str(exc))
            return
        if command in REMOTE_MUTATION_COMMANDS:
            expected = f"RUN {command}"
            if self.automation_confirm.get().strip() != expected:
                module.messagebox.showwarning(
                    "Remote action confirmation",
                    f"Type exactly: {expected}\n\nThis is an extra GUI guard; it does not replace approval/reservation validation.",
                )
                return
        self._automation_running = True
        self.automation_status.set("Running…")
        self.automation_run_button.config(state="disabled")
        self.automation_output.insert("end", f"\n$ {cli_preview(argv)}\n")

        def worker():
            buffer = io.StringIO()
            error = None
            try:
                with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                    automation_cli.main(argv)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    error = str(exc)
            except Exception as exc:  # GUI must surface unexpected connector/runtime errors.
                error = f"{type(exc).__name__}: {exc}"
            self.root.after(0, self._finish_automation, buffer.getvalue(), error)

        threading.Thread(target=worker, daemon=True, name=f"automation-{command}").start()

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "automation_page"):
            return
        # Keep command names/approval phrases invariant while localizing surrounding UI later.
        self.main_tabs.tab(self.automation_page, text="Automation")

    def set_running(self, running):
        base_set_running(self, running)
        if hasattr(self, "automation_run_button"):
            self.automation_run_button.config(state="disabled" if running or self._automation_running else "normal")

    module.App.build = build
    module.App.apply_language = apply_language
    module.App.set_running = set_running
    module.App.rebuild_automation_form = rebuild_automation_form
    module.App.automation_values = automation_values
    module.App.refresh_automation_preview = refresh_automation_preview
    module.App.clear_automation_output = clear_automation_output
    module.App._finish_automation = _finish_automation
    module.App.run_automation_command = run_automation_command
