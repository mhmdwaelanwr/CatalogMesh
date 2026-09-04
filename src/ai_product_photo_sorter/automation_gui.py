"""Scrollable Tkinter Automation Center backed by the canonical automation CLI parser.

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

_TEXT = {
    "en": {"tab":"Automation","title":"Automation Center","hint":"Run the same capability set exposed by the CLI, with previews, approvals and audit visibility.","command":"Command","confirmation":"Confirmation","run":"Run command","clear":"Clear output","preview":"COMMAND PREVIEW","output":"OUTPUT","ready":"Ready","running":"Running…","completed":"Completed","failed":"Failed","browse":"Browse…","local_guard":"Local/read-only command. No extra GUI confirmation phrase is required."},
    "ar": {"tab":"الأتمتة","title":"مركز الأتمتة","hint":"شغّل نفس القدرات المتاحة في CLI مع المعاينة والموافقات وسجل التدقيق.","command":"الأمر","confirmation":"التأكيد","run":"تشغيل الأمر","clear":"مسح المخرجات","preview":"معاينة الأمر","output":"المخرجات","ready":"جاهز","running":"جاري التشغيل…","completed":"اكتمل","failed":"فشل","browse":"اختيار…","local_guard":"أمر محلي أو للقراءة فقط. لا يحتاج عبارة تأكيد إضافية من الواجهة."},
    "zh": {"tab":"自动化","title":"自动化中心","hint":"运行与 CLI 相同的能力，并提供预览、审批和审计可见性。","command":"命令","confirmation":"确认","run":"运行命令","clear":"清除输出","preview":"命令预览","output":"输出","ready":"就绪","running":"运行中…","completed":"已完成","failed":"失败","browse":"浏览…","local_guard":"本地/只读命令，不需要额外的 GUI 确认短语。"},
}

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

_DIRECTORY_NAMES = {"root", "shoot", "state_dir", "output", "source"}


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
    """Build CLI argv from GUI field values using canonical parser metadata."""
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
    # argparse remains the final authority on types, choices and required fields.
    automation_cli.build_parser().parse_args(argv)
    return argv


def cli_preview(argv: list[str]) -> str:
    return "catalogmesh-automation " + " ".join(shlex.quote(part) for part in argv)


def _wheel_units(event: Any) -> int:
    """Normalize Windows/macOS wheel events and Linux Button-4/5 events."""
    number = getattr(event, "num", None)
    if number == 4:
        return -3
    if number == 5:
        return 3
    delta = int(getattr(event, "delta", 0) or 0)
    if not delta:
        return 0
    # Windows commonly reports multiples of 120; macOS can report small deltas.
    return -max(1, min(4, abs(delta) // 120 or 1)) if delta > 0 else max(1, min(4, abs(delta) // 120 or 1))


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

        page = module.ttk.Frame(self.main_tabs, style="Panel.TFrame", padding=(14, 12))
        self.main_tabs.add(page, text="Automation")
        self.automation_page = page

        header = module.ttk.Frame(page, style="Card.TFrame", padding=(16, 14))
        header.pack(fill="x", pady=(0, 10))
        title_row = module.ttk.Frame(header, style="Card.TFrame")
        title_row.pack(fill="x")
        self.automation_title = module.ttk.Label(title_row, text="Automation Center", style="Metric.TLabel")
        self.automation_title.pack(side="left", anchor="w")
        module.ttk.Label(
            title_row,
            textvariable=self.automation_status,
            style="MetricName.TLabel",
        ).pack(side="right", anchor="e")
        self.automation_hint = module.ttk.Label(
            header,
            text=(
                "Every automation CLI command is available here from the same parser. "
                "Remote writes keep the exact approval + single-use reservation boundary."
            ),
            style="MetricName.TLabel",
            wraplength=980,
        )
        self.automation_hint.pack(anchor="w", pady=(3, 10))

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
        self.automation_command_box.pack(side="left", fill="x", expand=True)
        self.automation_command_box.bind("<<ComboboxSelected>>", lambda _event: self.rebuild_automation_form())

        # The command form can be taller than a laptop display. Keep the header
        # fixed and scroll the command body instead of forcing a larger window.
        scroll_shell = module.ttk.Frame(page, style="Panel.TFrame")
        scroll_shell.pack(fill="both", expand=True)
        self.automation_canvas = module.tk.Canvas(
            scroll_shell,
            bg=self.colors["panel"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.automation_scrollbar = module.ttk.Scrollbar(
            scroll_shell, orient="vertical", command=self.automation_canvas.yview
        )
        self.automation_canvas.configure(yscrollcommand=self.automation_scrollbar.set)
        self.automation_scrollbar.pack(side="right", fill="y")
        self.automation_canvas.pack(side="left", fill="both", expand=True)

        body = module.ttk.Frame(self.automation_canvas, style="Panel.TFrame", padding=(0, 0, 8, 14))
        self.automation_body = body
        self._automation_canvas_window = self.automation_canvas.create_window(
            (0, 0), window=body, anchor="nw"
        )
        body.bind(
            "<Configure>",
            lambda _event: self.automation_canvas.configure(scrollregion=self.automation_canvas.bbox("all")),
        )
        self.automation_canvas.bind(
            "<Configure>",
            lambda event: self.automation_canvas.itemconfigure(self._automation_canvas_window, width=event.width),
        )

        self.automation_form = module.ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
        self.automation_form.pack(fill="x")

        self.automation_guard = module.ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
        self.automation_guard.pack(fill="x", pady=(10, 0))
        self.automation_guard_label = module.ttk.Label(
            self.automation_guard,
            style="MetricName.TLabel",
            wraplength=980,
        )
        self.automation_guard_label.pack(anchor="w")
        self.automation_confirm_row = module.ttk.Frame(self.automation_guard, style="Card.TFrame")
        self.automation_confirm_row.pack(fill="x", pady=(8, 0))
        self.automation_confirm_label = module.ttk.Label(
            self.automation_confirm_row,
            text="Confirmation",
            style="MetricName.TLabel",
            width=16,
        )
        self.automation_confirm_label.pack(side="left")
        self.automation_confirm_entry = module.ttk.Entry(
            self.automation_confirm_row, textvariable=self.automation_confirm
        )
        self.automation_confirm_entry.pack(side="left", fill="x", expand=True)

        actions = module.ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
        actions.pack(fill="x", pady=(10, 0))
        self.automation_run_button = module.ttk.Button(
            actions, text="Run command", style="Accent.TButton", command=self.run_automation_command
        )
        self.automation_run_button.pack(side="left", padx=(0, 8))
        self.automation_clear_button = module.ttk.Button(
            actions, text="Clear output", style="Soft.TButton", command=self.clear_automation_output
        )
        self.automation_clear_button.pack(side="left")

        preview_card = module.ttk.Frame(body, style="Card.TFrame", padding=(16, 12))
        preview_card.pack(fill="both", expand=True, pady=(10, 0))
        self.automation_preview_label = module.ttk.Label(preview_card, text="COMMAND PREVIEW", style="Section.TLabel"); self.automation_preview_label.pack(anchor="w", pady=(0, 6))
        self.automation_preview = module.tk.Text(preview_card, height=3, wrap="word")
        self.automation_preview.pack(fill="x", pady=(0, 10))
        self.automation_output_label = module.ttk.Label(preview_card, text="OUTPUT", style="Section.TLabel"); self.automation_output_label.pack(anchor="w", pady=(0, 6))
        self.automation_output = module.tk.Text(preview_card, height=9, wrap="word")
        output_scroll = module.ttk.Scrollbar(preview_card, orient="vertical", command=self.automation_output.yview)
        self.automation_output.configure(yscrollcommand=output_scroll.set)
        output_scroll.pack(side="right", fill="y")
        self.automation_output.pack(fill="both", expand=True)

        def on_wheel(event):
            units = _wheel_units(event)
            if units:
                self.automation_canvas.yview_scroll(units, "units")
            return "break"

        def bind_wheel(_event):
            self.automation_canvas.bind_all("<MouseWheel>", on_wheel)
            self.automation_canvas.bind_all("<Button-4>", on_wheel)
            self.automation_canvas.bind_all("<Button-5>", on_wheel)

        def unbind_wheel(_event):
            self.automation_canvas.unbind_all("<MouseWheel>")
            self.automation_canvas.unbind_all("<Button-4>")
            self.automation_canvas.unbind_all("<Button-5>")

        self.automation_canvas.bind("<Enter>", bind_wheel)
        self.automation_canvas.bind("<Leave>", unbind_wheel)
        body.bind("<Enter>", bind_wheel)
        body.bind("<Leave>", unbind_wheel)
        self.rebuild_automation_form()

    def _browse_for_action(self, action):
        directory = (
            action.dest in _DIRECTORY_NAMES
            and action.dest not in {"output"}
            or (action.dest == "output" and self.automation_command.get() not in {"request-external-action"})
        )
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

        parser = command_parsers().get(command)
        description = (parser.description if parser else None) or "Configure the selected automation command."
        module.ttk.Label(
            self.automation_form,
            text=command.replace("-", " ").title(),
            style="Metric.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        module.ttk.Label(
            self.automation_form,
            text=description,
            style="MetricName.TLabel",
            wraplength=940,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

        for row_index, action in enumerate(parser_actions(command), 2):
            label_text = action.dest.replace("_", " ").title()
            if not action.option_strings:
                label_text += "  • required"
            module.ttk.Label(
                self.automation_form,
                text=label_text,
                style="MetricName.TLabel",
                width=22,
            ).grid(row=row_index, column=0, sticky="w", padx=(0, 8), pady=4)
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
                        text=_TEXT.get(self.lang, _TEXT["en"])["browse"],
                        style="Soft.TButton",
                        command=lambda current=action: _browse_for_action(self, current),
                    ).grid(row=row_index, column=2, padx=(8, 0), pady=4)
            self.automation_field_vars[action.dest] = variable
        self.automation_form.columnconfigure(1, weight=1)
        self.refresh_automation_preview()
        self.automation_canvas.yview_moveto(0)

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
            text = f"Complete the required fields to preview the command.\n{exc}"
        self.automation_preview.insert("1.0", text)
        command = self.automation_command.get()
        remote = command in REMOTE_MUTATION_COMMANDS
        if remote:
            expected = f"RUN {command}"
            self.automation_guard_label.config(
                text=(
                    "Remote mutation safety is unchanged: approval + reservation are mandatory. "
                    f"As an extra desktop guard, type exactly: {expected}"
                )
            )
            if not self.automation_confirm_row.winfo_manager():
                self.automation_confirm_row.pack(fill="x", pady=(8, 0))
        else:
            self.automation_guard_label.config(
                text=_TEXT.get(self.lang, _TEXT["en"])["local_guard"]
            )
            self.automation_confirm_row.pack_forget()

    def clear_automation_output(self):
        self.automation_output.delete("1.0", "end")
        self.automation_status.set(_TEXT.get(self.lang, _TEXT["en"])["ready"])

    def _finish_automation(self, output: str, error: str | None):
        self._automation_running = False
        self.automation_output.insert("end", output or "(no output)\n")
        self.automation_output.see("end")
        if error:
            self.automation_output.insert("end", f"\nERROR: {error}\n")
            self.automation_status.set(_TEXT.get(self.lang, _TEXT["en"])["failed"])
        else:
            self.automation_status.set(_TEXT.get(self.lang, _TEXT["en"])["completed"])
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
                    f"Type exactly: {expected}\n\nThis extra GUI guard does not replace approval/reservation validation.",
                )
                return
        self._automation_running = True
        self.automation_status.set(_TEXT.get(self.lang, _TEXT["en"])["running"])
        self.automation_run_button.config(state="disabled")
        self.automation_output.insert("end", f"\n$ {cli_preview(argv)}\n")
        self.automation_output.see("end")

        def worker():
            buffer = io.StringIO()
            error = None
            try:
                with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                    result = automation_cli.main(argv)
                if result not in (None, 0):
                    error = f"Command exited with status {result}"
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    error = str(exc)
            except Exception as exc:  # surface connector/runtime errors in the UI.
                error = f"{type(exc).__name__}: {exc}"
            self.root.after(0, self._finish_automation, buffer.getvalue(), error)

        threading.Thread(target=worker, daemon=True, name=f"automation-{command}").start()

    def apply_language(self):
        base_apply_language(self)
        if not hasattr(self, "automation_page"):
            return
        t = _TEXT.get(self.lang, _TEXT["en"])
        self.main_tabs.tab(self.automation_page, text=t["tab"])
        self.automation_title.configure(text=t["title"])
        self.automation_hint.configure(text=t["hint"])
        self.automation_command_label.configure(text=t["command"])
        self.automation_confirm_label.configure(text=t["confirmation"])
        self.automation_run_button.configure(text=t["run"])
        self.automation_clear_button.configure(text=t["clear"])
        self.automation_preview_label.configure(text=t["preview"])
        self.automation_output_label.configure(text=t["output"])
        if not self._automation_running:
            self.automation_status.set(t["ready"])
        self.rebuild_automation_form()

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
