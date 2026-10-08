"""GUI entry point: the start menu, port selection, then the controller."""

from __future__ import annotations

import argparse
import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

from ..core.devices import PortCheck, check_ports, connect, detect
from ..core.link import PortInfo, list_ports
from ..core.session import Session
from ..core.settings import Config, Options
from . import theme
from .controller import ControllerWindow
from .tasks import TaskRunner

log = logging.getLogger(__name__)


class App:
    def __init__(self, root: tk.Tk, config: Config, options: Options, sim: bool = False):
        self.root = root
        self.config = config
        self.options = options
        self.sim = sim
        self.tasks = TaskRunner(root)
        self.controller: Optional[ControllerWindow] = None
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self._build_start_menu()

    # ------------------------------------------------------------ start menu

    def _build_start_menu(self) -> None:
        root = self.root
        root.title("ECRIT Electroplating" + (" (simulated)" if self.sim else ""))
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        frm = tk.Frame(root, bg=theme.BG)
        frm.grid(row=0, column=0, padx=32, pady=24)
        self.start_frm = frm

        tk.Label(frm, text="ECRIT Electroplating", bg=theme.BG, fg="white",
                 font="Helvetica 16 bold").grid(row=0, column=0, pady=(0, 2))
        tk.Label(frm, text="Simulated boards" if self.sim else "Experiment setup", bg=theme.BG,
                 fg=theme.SUBTLE).grid(row=1, column=0, pady=(0, 10))
        self.ports_label = tk.Label(frm, bg=theme.BG, fg=theme.SUBTLE, justify="left", wraplength=320)
        self.ports_label.grid(row=2, column=0, pady=(0, 14))
        self._show_ports()

        self.start_btn = theme.accent_button(frm, "Start", self._start, width=22)
        self.start_btn.grid(row=3, column=0, sticky="ew", ipady=6, pady=3)
        self.ports_btn = theme.button(frm, "Configure Ports", self._configure_ports, width=22)
        self.ports_btn.grid(row=4, column=0, sticky="ew", ipady=2, pady=3)
        theme.button(frm, "Quit", self.quit, width=22).grid(row=5, column=0, sticky="ew", ipady=2, pady=3)
        self.status = tk.Label(frm, text="", bg=theme.BG, fg="white")
        self.status.grid(row=6, column=0, pady=(10, 0))

    def _show_ports(self) -> None:
        if self.sim:
            text = "Ports are not used with simulated boards."
        else:
            text = "\n".join(f"{name}: {port or 'auto-detect'}" for name, port in
                             (("ECRIT-HAT", self.options.arduino_port), ("Printer", self.options.printer_port)))
        self.ports_label.config(text=text)

    def _start(self) -> None:
        self.start_btn.config(state="disabled")
        self.ports_btn.config(state="disabled")
        self.status.config(text="Connecting...")

        def work() -> Session:
            if self.sim:
                from ..core.sim import sim_rig
                rig = sim_rig()
            else:
                rig = connect(self.options)
            session = Session(rig, self.config)
            try:
                session.start()
            except Exception:
                rig.close()
                raise
            return session

        self.tasks.submit(work, self._connected, self._connect_failed)

    def _connected(self, session: Session) -> None:
        log.info("HAT on %s, printer on %s", session.rig.hat.port, session.rig.printer.port)
        self.start_frm.destroy()
        self.controller = ControllerWindow(self.root, session, self.tasks, self.options, sim=self.sim)

    def _connect_failed(self, e: Exception) -> None:
        self.start_btn.config(state="normal")
        self.ports_btn.config(state="normal")
        self.status.config(text="")
        messagebox.showerror(title="Can't Start Program",
                             message=f"{e}\n\nCheck that both boards are plugged in and the power supply is on, "
                                     "or pick the ports with Configure Ports.")

    def _configure_ports(self) -> None:
        PortDialog(self.root, self.options, self.tasks, on_save=self._show_ports)

    def quit(self) -> None:
        controller = self.controller
        if controller is not None and controller.running:
            if not messagebox.askyesno(title="Quit", message="A run is in progress. Turn the output off and quit?"):
                return
            controller.stop_run()
        if controller is not None:
            controller.session.rig.close()
        self.root.destroy()


class PortDialog(tk.Toplevel):
    """Pick the HAT and printer ports. Unlisted paths (such as
    /dev/serial/by-id/...) can be typed in. Test opens the two selected
    ports and says whether the right board answers on each."""

    OK = theme.GOOD
    FAIL = theme.BAD

    def __init__(self, parent: tk.Misc, options: Options, tasks: TaskRunner,
                 on_save: Optional[Callable[[], None]] = None):
        super().__init__(parent, bg=theme.BG)
        self.title("Configure Ports")
        self.options = options
        self.tasks = tasks
        self.on_save = on_save
        self.transient(parent)
        self.resizable(True, False)

        try:
            ports: List[PortInfo] = list_ports()
        except Exception as e:  # pyserial missing or no port access
            log.warning("Could not list ports: %s", e)
            ports = []
        self.by_label: Dict[str, str] = {str(p): p.device for p in ports}
        labels = list(self.by_label)

        self.grid_columnconfigure(0, weight=1)
        tk.Label(self, text="Serial Ports", bg=theme.BG, fg="white", font="Helvetica 15 bold", anchor="w") \
            .grid(row=0, column=0, sticky="w", padx=22, pady=(16, 0))
        tk.Label(self, text="Pick the port each board is on, or type a path. Test checks that the right "
                            "board answers; Detect searches for both.",
                 bg=theme.BG, fg=theme.SUBTLE, anchor="w", justify="left", wraplength=620) \
            .grid(row=1, column=0, sticky="w", padx=22, pady=(2, 12))

        body = tk.Frame(self, bg=theme.BG)
        body.grid(row=2, column=0, sticky="nsew", padx=22)
        body.grid_columnconfigure(1, weight=1)
        self.hat, self.hat_result = self._port_row(body, 0, "ECRIT-HAT (Arduino)", labels)
        self.printer, self.printer_result = self._port_row(body, 2, "Printer", labels)
        self._select(self.hat, options.arduino_port)
        self._select(self.printer, options.printer_port)

        self.status = tk.Label(self, text="", bg=theme.BG, fg="white", anchor="w", justify="left")
        self.status.grid(row=3, column=0, sticky="ew", padx=22)
        tk.Frame(self, height=1, bg=theme.CARD_LINE).grid(row=4, column=0, sticky="ew", padx=22, pady=(10, 12))
        buttons = tk.Frame(self, bg=theme.BG)
        buttons.grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 16))
        buttons.grid_columnconfigure(2, weight=1)
        self.detect_btn = theme.button(buttons, "Detect", self._detect, width=8)
        self.detect_btn.grid(row=0, column=0, padx=(0, 6), ipady=2)
        self.test_btn = theme.button(buttons, "Test", self._test, width=8)
        self.test_btn.grid(row=0, column=1, ipady=2)
        theme.button(buttons, "Cancel", self.destroy, width=8).grid(row=0, column=3, padx=(0, 6), ipady=2)
        self.confirm_btn = theme.accent_button(buttons, "Confirm", self._confirm, width=8)
        self.confirm_btn.grid(row=0, column=4, ipady=2)

    def _port_row(self, parent: tk.Frame, row: int, name: str, labels: List[str]):
        tk.Label(parent, text=name, bg=theme.BG, fg="white", font="Helvetica 11 bold", anchor="w") \
            .grid(row=row, column=0, sticky="w", padx=(0, 12))
        box = ttk.Combobox(parent, values=labels, width=60, font=("Helvetica", 11))
        box.grid(row=row, column=1, sticky="ew", pady=(4, 0))
        result = tk.Label(parent, text="", bg=theme.BG, anchor="w", justify="left", wraplength=480)
        result.grid(row=row + 1, column=1, sticky="w", pady=(0, 6))
        # A result is only good for the port it was taken on.
        clear = lambda _event: result.config(text="")
        box.bind("<<ComboboxSelected>>", clear)
        box.bind("<KeyRelease>", clear)
        return box, result

    def _select(self, box: ttk.Combobox, device: str) -> None:
        for label, dev in self.by_label.items():
            if dev == device:
                box.set(label)
                return
        box.set(device)

    def _device(self, box: ttk.Combobox) -> str:
        text = box.get().strip()
        return self.by_label.get(text, text)

    def _busy(self, busy: bool, message: str = "") -> None:
        state = "disabled" if busy else "normal"
        for button in (self.detect_btn, self.test_btn, self.confirm_btn):
            button.config(state=state)
        self.status.config(text=message, fg="white")

    def _show_result(self, label: tk.Label, check: Optional[PortCheck]) -> None:
        if check is None:
            label.config(text="")
        else:
            label.config(text=("\u2713 " if check.ok else "\u2717 ") + check.detail,
                         fg=self.OK if check.ok else self.FAIL)

    def _detect(self) -> None:
        self._busy(True, "Probing ports...")
        self._show_result(self.hat_result, None)
        self._show_result(self.printer_result, None)

        def done(found) -> None:
            if not self.winfo_exists():
                return
            self._busy(False)
            if found.hat:
                self._select(self.hat, found.hat)
            if found.printer:
                self._select(self.printer, found.printer)
            self.status.config(text=f"HAT: {found.hat or 'not found'}   Printer: {found.printer or 'not found'}")

        self.tasks.submit(detect, done, self._failed)

    def _test(self) -> None:
        hat, printer = self._device(self.hat), self._device(self.printer)
        self._busy(True, "Testing the selected ports...")
        self._show_result(self.hat_result, None)
        self._show_result(self.printer_result, None)

        def done(checks: Tuple[PortCheck, PortCheck]) -> None:
            if not self.winfo_exists():
                return
            self._busy(False)
            hat_check, printer_check = checks
            self._show_result(self.hat_result, hat_check)
            self._show_result(self.printer_result, printer_check)
            if hat_check.ok and printer_check.ok:
                self.status.config(text="Both ports are correct.", fg=self.OK)
            else:
                self.status.config(text="Check the ports marked \u2717, or try Detect.", fg=self.FAIL)

        self.tasks.submit(lambda: check_ports(hat, printer), done, self._failed)

    def _failed(self, e: Exception) -> None:
        if self.winfo_exists():
            self._busy(False)
            self.status.config(text=str(e), fg=self.FAIL)

    def _confirm(self) -> None:
        hat, printer = self._device(self.hat), self._device(self.printer)
        if not hat or not printer:
            messagebox.showerror(parent=self, message="You must select a port for both devices")
            return
        if hat == printer:
            messagebox.showerror(parent=self, message="Arduino Port and Printer Port can NOT be the same")
            return
        self.options.arduino_port, self.options.printer_port = hat, printer
        self.options.save()
        if self.on_save is not None:
            self.on_save()
        self.destroy()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="ECRIT electroplating rig.")
    parser.add_argument("--sim", action="store_true", help="use simulated boards (no hardware)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log serial traffic")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    root = tk.Tk()
    theme.apply(root)
    App(root, Config.load(), Options.load(), sim=args.sim)
    root.mainloop()
