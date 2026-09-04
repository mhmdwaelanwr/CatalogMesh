"""Safety and lifecycle hardening for the CatalogMesh rclone GUI surface."""
from __future__ import annotations

from pathlib import Path
import subprocess
import threading
from typing import Any, Callable

from .rclone_gui import _TEXT
from .rclone_storage import (
    RcloneError,
    TransferOptions,
    append_sync_audit,
    list_remotes,
    remote_target,
    rclone_version,
    stream_transfer,
    test_remote,
)


def apply_rclone_gui_hardening(module: Any) -> None:
    """Harden Tk callbacks, auto-copy arming, and narrow-width action layout."""
    base_build = module.App.build
    base_start = module.App.start
    rclone_set_running = module.App.set_running

    def storage_text(self):
        return _TEXT.get(self.lang, _TEXT["en"])

    def schedule_gui(self, callback: Callable[[], None], delay: int = 0) -> bool:
        """Schedule a Tk callback without crashing a worker during teardown."""
        try:
            self.root.after(int(delay), callback)
            return True
        except (module.tk.TclError, RuntimeError):
            return False

    def build(self):
        base_build(self)
        self._rclone_auto_copy_process = None

        # The original horizontal pack row can clip the Upload/Cancel actions
        # on small windows. Keep the same real ttk widgets and lay them out in
        # two responsive rows; no Canvas/re-parenting tricks are involved.
        buttons = [
            getattr(self, "rclone_test_button", None),
            getattr(self, "rclone_preview_button", None),
            getattr(self, "rclone_upload_button", None),
            getattr(self, "rclone_cancel_button", None),
        ]
        buttons = [button for button in buttons if button is not None]
        if buttons:
            actions = buttons[0].master
            other_children = [child for child in actions.winfo_children() if child not in buttons]
            for child in actions.winfo_children():
                try:
                    child.pack_forget()
                except module.tk.TclError:
                    pass
            actions.columnconfigure(0, weight=1)
            actions.columnconfigure(1, weight=1)
            for index, button in enumerate(buttons):
                button.grid(
                    row=index // 2,
                    column=index % 2,
                    sticky="ew",
                    padx=(0 if index % 2 == 0 else 4, 4 if index % 2 == 0 else 0),
                    pady=(0, 5),
                )
            for child in other_children:
                child.grid(row=2, column=0, columnspan=2, sticky="w", pady=(1, 0))

    def start(self):
        before = getattr(self, "p", None)
        result = base_start(self)
        after = getattr(self, "p", None)

        if after is not before and after is not None:
            # Arm only for a process actually created by this invocation.
            self._rclone_auto_copy_process = after
        elif after is None or after.poll() is not None:
            # Validation/early-return paths must never leave a stale arm.
            self._rclone_auto_copy_process = None
        # If the same process is still running, preserve the existing arm.
        return result

    def set_running(self, running):
        # Neutralize the legacy generic transition detector, then use the
        # process identity armed by start() above.
        self._sorter_was_running = False
        rclone_set_running(self, running)
        self._sorter_was_running = False
        if running:
            return

        process = getattr(self, "_rclone_auto_copy_process", None)
        if process is None:
            return
        self._rclone_auto_copy_process = None
        current = getattr(self, "p", None)
        succeeded = process is current and process.poll() == 0
        auto = "rclone_auto" in self.vars and bool(self.vars["rclone_auto"].get())
        if succeeded and auto:
            self.append_rclone_log(storage_text(self)["auto_start"])
            schedule_gui(
                self,
                lambda: self.start_rclone_transfer(dry_run=False, automatic=True),
                100,
            )

    def refresh_rclone_remotes(self):
        if getattr(self, "rclone_busy", False):
            return
        self.rclone_status.set(storage_text(self)["checking"])
        self.rclone_binary_status.set(storage_text(self)["checking"])

        def worker():
            try:
                version = rclone_version()
                remotes = list_remotes()
                error = None
            except (RcloneError, OSError, ValueError, subprocess.SubprocessError) as exc:
                version, remotes, error = "", (), str(exc)

            def finish(version=version, remotes=remotes, error=error):
                if error:
                    self.rclone_binary_status.set(storage_text(self)["not_found"])
                    self.rclone_status.set(storage_text(self)["idle"])
                    self.append_rclone_log(error)
                    return
                self.rclone_binary_status.set(version)
                self.rclone_remote_box.configure(values=remotes)
                current = self.vars["rclone_remote"].get()
                if current not in remotes:
                    self.vars["rclone_remote"].set(remotes[0] if remotes else "")
                self.rclone_status.set(
                    storage_text(self)["remotes_found"].format(count=len(remotes))
                )

            schedule_gui(self, finish)

        threading.Thread(target=worker, daemon=True).start()

    def test_rclone_remote(self):
        if getattr(self, "rclone_busy", False):
            return
        try:
            _output, target = self.current_rclone_target()
        except ValueError as exc:
            module.messagebox.showerror(storage_text(self)["error_title"], str(exc))
            return
        self.set_rclone_busy(True)
        self.rclone_status.set(storage_text(self)["testing"])

        def worker():
            try:
                test_remote(target)
                error = None
            except (RcloneError, OSError, ValueError, subprocess.SubprocessError) as exc:
                error = str(exc)

            def finish(error=error):
                self.set_rclone_busy(False)
                if error:
                    self.rclone_status.set(storage_text(self)["failed"])
                    self.append_rclone_log(error)
                    module.messagebox.showerror(storage_text(self)["error_title"], error)
                else:
                    self.rclone_status.set(storage_text(self)["success"])

            schedule_gui(self, finish)

        threading.Thread(target=worker, daemon=True).start()

    def start_rclone_transfer(self, dry_run=False, automatic=False):
        if getattr(self, "rclone_busy", False):
            return
        try:
            output, target = self.current_rclone_target()
            mode = "copy" if automatic else self.vars["rclone_mode"].get().strip().lower()
            options = TransferOptions(
                mode=mode,
                dry_run=bool(dry_run),
                transfers=int(self.vars["rclone_transfers"].get() or "4"),
                checkers=int(self.vars["rclone_checkers"].get() or "8"),
                bwlimit=self.vars["rclone_bwlimit"].get(),
            ).validated()
        except (ValueError, RcloneError) as exc:
            module.messagebox.showerror(storage_text(self)["error_title"], str(exc))
            return

        if automatic and options.mode != "copy":
            # Defense in depth: automatic transfer is copy-only.
            options = TransferOptions(
                mode="copy",
                dry_run=options.dry_run,
                transfers=options.transfers,
                checkers=options.checkers,
                bwlimit=options.bwlimit,
            )

        if options.mode == "sync" and not options.dry_run:
            phrase = storage_text(self)["sync_phrase"].format(target=target)
            entered = module.simpledialog.askstring(
                storage_text(self)["sync_title"],
                storage_text(self)["sync_prompt"].format(phrase=phrase),
                parent=self.root,
            )
            if entered != phrase:
                return

        self.set_rclone_busy(True)
        status_key = "running_preview" if options.dry_run else (
            "running_sync" if options.mode == "sync" else "running_copy"
        )
        self.rclone_status.set(storage_text(self)[status_key])
        self.append_rclone_log(
            f"{options.mode.upper()} {output} -> {target}"
            + (" [DRY-RUN]" if options.dry_run else "")
        )

        def on_line(line):
            schedule_gui(self, lambda value=line: self.append_rclone_log(value))

        def on_process(process):
            self.rclone_process = process

        def worker():
            try:
                code = stream_transfer(
                    output,
                    target,
                    options=options,
                    on_line=on_line,
                    on_process=on_process,
                )
                error = None
            except (RcloneError, OSError, ValueError, subprocess.SubprocessError) as exc:
                code, error = -1, str(exc)
            try:
                append_sync_audit(
                    output,
                    target=target,
                    mode=options.mode,
                    dry_run=options.dry_run,
                    returncode=code,
                    automatic=automatic,
                )
            except OSError:
                pass

            def finish(code=code, error=error):
                self.rclone_process = None
                self.set_rclone_busy(False)
                if error:
                    self.append_rclone_log(error)
                    self.rclone_status.set(storage_text(self)["failed"])
                    module.messagebox.showerror(storage_text(self)["error_title"], error)
                elif code == 0:
                    self.rclone_status.set(
                        storage_text(self)["preview_done"]
                        if options.dry_run
                        else storage_text(self)["success"]
                    )
                else:
                    self.rclone_status.set(
                        storage_text(self)["cancelled"]
                        if code < 0
                        else storage_text(self)["failed"]
                    )

            schedule_gui(self, finish)

        threading.Thread(target=worker, daemon=True).start()

    module.App.build = build
    module.App.start = start
    module.App.set_running = set_running
    module.App.refresh_rclone_remotes = refresh_rclone_remotes
    module.App.test_rclone_remote = test_rclone_remote
    module.App.start_rclone_transfer = start_rclone_transfer
    module.App._schedule_storage_gui = schedule_gui
