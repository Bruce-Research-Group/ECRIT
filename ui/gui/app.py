"""GUI entry point: the start menu, port selection, then the controller."""

from __future__ import annotations

import argparse
import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from ..core.devices import connect, detect
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
        root.title("Electrochemistry Experiment Setup" + (" (simulated)" if self.sim else ""))
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        frm = tk.Frame(root, bg=theme.BG)
        frm.grid(row=0, column=0, padx=50, pady=50)
        self.start_frm = frm

        self.start_btn = tk.Button(frm, text="Start", command=self._start, width=20, bg=theme.ACCENT, fg="white")
        self.start_btn.grid(column=0, row=0, pady=50, padx=(75, 40))
        self.ports_btn = tk.Button(frm, text="Configure\nPorts", command=self._configure_ports)
        self.ports_btn.grid(column=4, row=4, ipady=10, padx=50)
        tk.Button(frm, text="Quit", command=self.quit, width=15).grid(column=0, row=1, padx=(75, 40), pady=(20, 50))
        self.status = tk.Label(frm, text="", bg=theme.BG, fg="white")
        self.status.grid(column=0, row=5, columnspan=5)

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
        self.root.title("Electroplating GUI" + (" (simulated)" if self.sim else ""))
        self.controller = ControllerWindow(self.root, session, self.tasks, self.options)

    def _connect_failed(self, e: Exception) -> None:
        self.start_btn.config(state="normal")
        self.ports_btn.config(state="normal")
        self.status.config(text="")
        messagebox.showerror(title="Can't Start Program",
                             message=f"{e}\n\nCheck that both boards are plugged in and the power supply is on, "
                                     "or pick the ports with Configure Ports.")

    def _configure_ports(self) -> None:
        PortDialog(self.root, self.options, self.tasks)

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
    /dev/serial/by-id/...) can be typed in."""

    def __init__(self, parent: tk.Misc, options: Options, tasks: TaskRunner):
        super().__init__(parent)
        self.title("Select Ports")
        self.options = options
        self.tasks = tasks
        self.transient(parent)

        try:
            ports: List[PortInfo] = list_ports()
        except Exception as e:  # pyserial missing or no port access
            log.warning("Could not list ports: %s", e)
            ports = []
        self.by_label: Dict[str, str] = {str(p): p.device for p in ports}
        labels = list(self.by_label)

        ttk.Label(self, text="Select Arduino Port", style="Dialog.TLabel").grid(column=0, row=0, padx=5, pady=5)
        ttk.Label(self, text="Select Printer Port", style="Dialog.TLabel").grid(column=0, row=1, padx=5, pady=5)
        self.hat = ttk.Combobox(self, values=labels, width=50)
        self.hat.grid(column=2, row=0, padx=5, pady=5)
        self.printer = ttk.Combobox(self, values=labels, width=50)
        self.printer.grid(column=2, row=1, padx=5, pady=5)
        self._select(self.hat, options.arduino_port)
        self._select(self.printer, options.printer_port)

        buttons = ttk.Frame(self)
        buttons.grid(column=0, row=2, columnspan=3, pady=5)
        self.detect_btn = tk.Button(buttons, text="Detect", command=self._detect)
        self.detect_btn.grid(column=0, row=0, padx=5)
        tk.Button(buttons, text="Confirm", command=self._confirm).grid(column=1, row=0, padx=5)
        tk.Button(buttons, text="Cancel", command=self.destroy).grid(column=2, row=0, padx=5)
        self.status = ttk.Label(self, text="", style="Dialog.TLabel")
        self.status.grid(column=0, row=3, columnspan=3)

    def _select(self, box: ttk.Combobox, device: str) -> None:
        for label, dev in self.by_label.items():
            if dev == device:
                box.set(label)
                return
        box.set(device)

    def _device(self, box: ttk.Combobox) -> str:
        text = box.get().strip()
        return self.by_label.get(text, text)

    def _detect(self) -> None:
        self.detect_btn.config(state="disabled")
        self.status.config(text="Probing ports...")

        def done(found) -> None:
            if not self.winfo_exists():
                return
            self.detect_btn.config(state="normal")
            if found.hat:
                self._select(self.hat, found.hat)
            if found.printer:
                self._select(self.printer, found.printer)
            self.status.config(text=f"HAT: {found.hat or 'not found'}   Printer: {found.printer or 'not found'}")

        self.tasks.submit(detect, done)

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
        self.destroy()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="ECRIT electroplating rig.")
    parser.add_argument("--sim", action="store_true", help="use simulated boards (no hardware)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log serial traffic")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    root = tk.Tk()
    theme.apply(root)
    ttk.Style(root).configure("Dialog.TLabel", foreground="black", background="")
    App(root, Config.load(), Options.load(), sim=args.sim)
    root.mainloop()
