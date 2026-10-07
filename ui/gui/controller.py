"""The main window: the controller page, the parameter page, and the run.

Controller page: home, jog, set the baseline height and the geometric areas.
Parameter page: distance, duration, current or voltage, then start.
A run opens a live readout with a cancel button; when it ends the results are
saved and plotted.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ..core.plating import PlatingRun, RunResult, Sample
from ..core.session import Session
from ..core.settings import Options
from . import theme
from .tasks import TaskRunner

log = logging.getLogger(__name__)

STEP_SIZES = (("0.1", 0.1), ("1", 1.0), ("10", 10.0), ("100", 100.0))


class ControllerWindow:
    def __init__(self, root: tk.Tk, session: Session, tasks: TaskRunner, options: Options):
        self.root = root
        self.session = session
        self.tasks = tasks
        self.options = options
        self.run: Optional[PlatingRun] = None
        self.step = tk.DoubleVar(root, 1.0)

        self.controller_frames = []
        self.param_frm: Optional[ttk.Frame] = None
        self.run_window: Optional[tk.Toplevel] = None
        self.show_controller()

    @property
    def running(self) -> bool:
        return self.run is not None

    def stop_run(self) -> None:
        if self.run is not None:
            self.run.stop()

    # ------------------------------------------------------------ controller page

    def show_controller(self) -> None:
        if self.param_frm is not None:
            self.param_frm.grid_forget()
        root = self.root
        root.wm_minsize(width=650, height=550)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        control_frm = tk.Frame(root, bg=theme.BG, border=5, padx=20, pady=20)
        control_frm.grid(column=0, row=0)
        control_frm.grid_columnconfigure(list(range(12)), weight=2)
        control_frm.grid_rowconfigure(list(range(12)), weight=2)
        btn_frm = tk.Frame(root, bg=theme.PANEL, border=5, padx=20, pady=20)
        btn_frm.grid(column=0, row=1, ipadx=150)
        btn_frm.grid_columnconfigure(list(range(15)), weight=1)
        self.controller_frames = [control_frm, btn_frm]

        tk.Button(control_frm, text="Home", width=5, command=self._home).grid(row=3, column=0, padx=(0, 100))

        ttk.Label(control_frm, text="Select Printer Step Size (mm):").grid(row=3, column=1, padx=5, pady=5)
        for i, (label, value) in enumerate(STEP_SIZES):
            ttk.Radiobutton(control_frm, text=label, value=value, variable=self.step) \
                .grid(row=4 + i, column=1, sticky="w", padx=5, pady=5)

        # X/Y pad. Y is flipped: the up arrow moves the bed away (-Y).
        xy_frm = tk.Frame(control_frm, bg=theme.PAD, padx=20, border=5, relief="ridge")
        xy_frm.grid(column=7, row=4, rowspan=20, ipady=2)
        ttk.Label(xy_frm, text="x-axis").grid(row=5, column=2, padx=5, pady=5)
        self._jog_button(xy_frm, "←", "x", -1).grid(row=5, column=3, padx=5, pady=5)
        self._jog_button(xy_frm, "→", "x", +1).grid(row=5, column=5, padx=5, pady=5)
        self._jog_button(xy_frm, "↑", "y", -1).grid(row=4, column=4, padx=5, pady=5)
        self._jog_button(xy_frm, "↓", "y", +1).grid(row=6, column=4, padx=5, pady=5)
        ttk.Label(xy_frm, text="y-axis").grid(row=7, column=4, padx=5, pady=5)

        z_frm = tk.Frame(control_frm, bg=theme.PAD, padx=20, border=5, relief="ridge")
        z_frm.grid(column=8, row=4, rowspan=20, ipady=20)
        self._jog_button(z_frm, "➚", "z", +1).grid(row=4, column=7, padx=20, pady=5)
        self._jog_button(z_frm, "➘", "z", -1).grid(row=6, column=7, padx=20, pady=5)
        ttk.Label(z_frm, text="z-axis").grid(row=7, column=7, padx=5, pady=5, sticky="s")

        self.position_label = tk.Label(btn_frm, fg="white", bg=theme.PANEL, font="Helvetica")
        self.position_label.grid(row=9, column=1, padx=5, pady=15)
        tk.Button(btn_frm, text="Set Baseline Height", width=20, command=self._set_baseline) \
            .grid(row=10, column=1, padx=5, pady=5)
        tk.Button(btn_frm, text="Go To Start Point", width=20, command=self._go_to_start_point) \
            .grid(row=11, column=1, padx=5, pady=5)

        self.points_label = tk.Label(btn_frm, fg="white", bg=theme.PANEL, font="Helvetica")
        self.points_label.grid(row=9, column=8, padx=5, pady=15)
        self.set_point_btn = tk.Button(btn_frm, text="Set Geometric Area", width=20, command=self._add_point)
        self.set_point_btn.grid(row=10, column=8, padx=5, pady=5)
        self.undo_btn = tk.Button(btn_frm, text="↩ Undo Geometric Area", command=self._undo_point)
        self.undo_btn.grid(row=11, column=8)

        tk.Button(btn_frm, text="Next", width=20, command=self._next, bg=theme.ACCENT, fg="white",
                  font="Helvetica 10 bold").grid(row=12, column=9, pady=(50, 0), ipadx=10, padx=(75, 0))
        self._refresh()

    def _jog_button(self, parent, text, axis, sign) -> tk.Button:
        return tk.Button(parent, text=text, width=2, command=lambda: self._jog(axis, sign))

    def _device(self, fn, on_done=None) -> None:
        """Queue a session call on the device thread, then refresh the labels."""
        def done(result):
            self._refresh()
            if on_done is not None:
                on_done(result)
        self.tasks.submit(fn, done)

    def _home(self) -> None:
        self._device(self.session.home)

    def _jog(self, axis: str, sign: int) -> None:
        amount = sign * self.step.get()
        self._device(lambda: self.session.jog(axis, amount))

    def _go_to_start_point(self) -> None:
        self._device(self.session.go_to_start_point)

    # Marking goes through the device thread too, so it sees the position
    # after any jog still queued ahead of it.
    def _set_baseline(self) -> None:
        self._device(self.session.set_baseline, lambda z: log.info("Baseline set at Z %g", z))

    def _add_point(self) -> None:
        def done(added):
            if not added:
                log.info("A point is already set at that position")
        self._device(self.session.add_point, done)

    def _undo_point(self) -> None:
        self._device(self.session.undo_point, lambda p: log.info("Removed point %s", p))

    def _refresh(self) -> None:
        if not self.controller_frames or not self.position_label.winfo_exists():
            return
        pos = self.session.position
        self.position_label.config(text=f"X {pos['x']:g}   Y {pos['y']:g}   Z {pos['z']:g}")
        count = len(self.session.points)
        self.points_label.config(text=f"{count} points set" if count else "0")
        self.undo_btn.config(state="normal" if count else "disabled")
        # Greyed out until a baseline is set, as a hint. Still clickable.
        self.set_point_btn.config(fg="black" if self.session.baseline_set or count else theme.MUTED)

    def _next(self) -> None:
        if not self.session.points:
            messagebox.showwarning(title="Wait!", message="Cannot Set Parameters Without Setting ALL Geometric Areas!")
            return
        for frm in self.controller_frames:
            frm.destroy()
        self.controller_frames = []
        self.show_params()

    # ------------------------------------------------------------ parameter page

    def show_params(self) -> None:
        s = self.session
        self.root.wm_minsize(width=600, height=200)
        frm = ttk.Frame(self.root, style="TFrame")
        frm.grid(row=0, column=0)
        self.param_frm = frm

        self.inputs = {}
        rows = (("distance", "Distance Between WE and CE (mm):", s.distance),
                ("duration", "Electrodeposition Time (sec):", s.duration),
                ("current", "Set a Current (mA):", s.target_current),
                ("voltage", "Set a Voltage (V):", s.target_voltage))
        self.input_labels = {}
        for row, (key, text, value) in enumerate(rows):
            label = ttk.Label(frm, text=text)
            label.grid(row=row, column=0, sticky="w", padx=5, pady=5)
            entry = ttk.Entry(frm, width=8)
            entry.insert(0, f"{value:g}")
            entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)
            self.inputs[key] = entry
            self.input_labels[key] = label

        ttk.Label(frm, text="Set Mode:").grid(row=0, columnspan=2, column=8, padx=40, pady=5)
        self.voltage_btn = tk.Button(frm, text="Voltage Mode", width=10, command=lambda: self._set_mode(False))
        self.voltage_btn.grid(row=1, column=8, padx=(15, 5), pady=5, ipadx=2)
        self.current_btn = tk.Button(frm, text="Current Mode", width=10, command=lambda: self._set_mode(True))
        self.current_btn.grid(row=1, column=9, padx=5, pady=5, ipadx=2)

        self.start_btn = tk.Button(frm, text="▶ START ELECTROPLATING!", command=self._start_run,
                                   bg=theme.ACCENT, fg="white", font="Helvetica 10 bold")
        self.start_btn.grid(row=11, column=8, ipadx=5, columnspan=3, pady=(15, 15))
        self.back_btn = tk.Button(frm, text="Go\nBack", width=10, command=self._back, bg=theme.BACK, fg="white")
        self.back_btn.grid(column=0, row=11, pady=(15, 10), sticky="w", padx=(10, 0))
        self._apply_mode()

    def _set_mode(self, current_mode: bool) -> None:
        self.session.current_mode = current_mode
        self._apply_mode()

    def _apply_mode(self) -> None:
        current = self.session.current_mode
        for key, enabled in (("current", current), ("voltage", not current)):
            self.inputs[key].config(state="normal" if enabled else "disabled")
            self.input_labels[key].config(state="normal" if enabled else "disabled")
        self.current_btn.config(bg=theme.SELECTED if current else "white")
        self.voltage_btn.config(bg="white" if current else theme.SELECTED)

    def _back(self) -> None:
        self._read_inputs(quiet=True)
        self.param_frm.destroy()
        self.param_frm = None
        self.show_controller()

    def _read_inputs(self, quiet: bool = False) -> bool:
        """Copy the entries into the session. False (after telling the user)
        if one of them is not a number."""
        s = self.session
        fields = [("distance", "distance", "distance"), ("duration", "duration", "duration")]
        fields.append(("current", "target_current", "current") if s.current_mode
                      else ("voltage", "target_voltage", "voltage"))
        for key, attr, name in fields:
            text = self.inputs[key].get().strip()
            try:
                setattr(s, attr, float(text))
            except ValueError:
                if not quiet:
                    messagebox.showerror(message=f"Please input proper {name} value that contains no symbols "
                                                 f"or letters aside from '.' and numbers.")
                    return False
        return True

    def _start_run(self) -> None:
        if self.running or not self._read_inputs():
            return
        try:
            params = self.session.run_params()
        except ValueError as e:
            messagebox.showerror(title="Cannot start", message=str(e))
            return

        self.start_btn.config(state="disabled")
        self.back_btn.config(state="disabled")
        self._open_run_window(len(params.points), params.duration)
        self.run = PlatingRun(self.session.rig, params,
                              on_event=lambda kind, payload: self.tasks.post(lambda: self._on_run_event(kind, payload)))
        self.tasks.submit(self.run.run, self._run_finished, self._run_crashed)

    # ------------------------------------------------------------ the run

    def _open_run_window(self, points: int, duration: float) -> None:
        top = tk.Toplevel(self.root)
        top.title("Electroplating")
        top.protocol("WM_DELETE_WINDOW", self._cancel)
        frm = ttk.Frame(top, style="TFrame")
        frm.grid()
        self.run_window = top
        self.run_points = points
        self.run_duration = duration
        self.run_labels = {}
        rows = (("state", "Starting..."), ("current", "Current: no reading yet"),
                ("voltage", "Output Voltage: no reading yet"), ("target", "Target Voltage: no reading yet"),
                ("time", "Time left: no reading yet"))
        for row, (key, text) in enumerate(rows):
            label = tk.Label(frm, text=text)
            label.grid(row=row, column=0, sticky="w", padx=5, pady=5)
            self.run_labels[key] = label
        self.cancel_btn = tk.Button(frm, text="Cancel Experiment", bg=theme.CANCEL, command=self._cancel)
        self.cancel_btn.grid(row=len(rows), column=0, padx=20, pady=5)

    def _cancel(self) -> None:
        if self.run is None:
            return
        self.cancel_btn.config(state="disabled", bg=theme.CANCELLED)
        self.run_labels["state"].config(text="Cancelling...")
        self.run.stop()

    def _on_run_event(self, kind: str, payload) -> None:
        if self.run_window is None or not self.run_window.winfo_exists():
            return
        labels = self.run_labels
        if kind == "state":
            labels["state"].config(text=str(payload))
        elif kind == "point":
            i, x, y = payload
            labels["state"].config(text=f"Point {i + 1}/{self.run_points} at ({x:g}, {y:g})")
        elif kind == "sample":
            s: Sample = payload
            labels["current"].config(text=f"current: {s.current_mA:g}")
            labels["voltage"].config(text=f"voltage: {s.voltage_V:g}")
            labels["target"].config(text=f"target voltage: {s.target_V:g}")
            labels["time"].config(text=f"time left: {max(0, int(self.run_duration - s.t_point))}")

    def _close_run_window(self) -> None:
        self.run = None
        if self.run_window is not None and self.run_window.winfo_exists():
            self.run_window.destroy()
        self.run_window = None
        if self.param_frm is not None:
            self.start_btn.config(state="normal")
            self.back_btn.config(state="normal")

    def _run_crashed(self, e: Exception) -> None:
        self._close_run_window()
        messagebox.showerror(title="Run failed", message=str(e))

    def _run_finished(self, result: RunResult) -> None:
        self._close_run_window()
        # The run moved the head; read back where it ended up.
        self.tasks.submit(self.session.sync_position, lambda _: None, lambda e: log.warning("%s", e))

        if result.error:
            messagebox.showerror(title="Run failed", message=result.summary())
        elif result.stopped:
            messagebox.showwarning(title="Run stopped", message=result.summary())
        self._save(result)
        if result.samples:
            self._show_graph(result)

    def _save(self, result: RunResult) -> None:
        """Ask where the CSV and log go, remembering the folder."""
        folder = self.options.csv_filepath
        if folder and Path(folder).is_dir():
            keep = messagebox.askyesnocancel(title="Save File",
                                             message=f"Save {result.csv_path.name} to {folder}?")
        else:
            keep = False
        if keep is None:
            if messagebox.askyesno(title="Save File", message="Are you sure you don't want to save this file?\n\n"
                                                              f"It stays in {result.csv_path.parent}."):
                return
            keep = False

        try:
            if keep:
                result.move_to(Path(folder))
            else:
                chosen = filedialog.asksaveasfilename(initialdir=folder or None, initialfile=result.csv_path.name,
                                                      defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
                if not chosen:
                    messagebox.showinfo(title="Not saved", message=f"The files stay in {result.csv_path.parent}.")
                    return
                result.save_as(Path(chosen))
        except OSError as e:
            messagebox.showerror(title="File Save Error",
                                 message=f"Could not move the files: {e}\n\nThey are still in {result.csv_path.parent}.")
            return

        self.options.csv_filepath = str(result.csv_path.parent)
        self.options.save()
        messagebox.showinfo(title="File Saved!", message=f"Saved to {result.csv_path}")

    def _show_graph(self, result: RunResult) -> None:
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from ..core.plot import make_figure
        except ImportError as e:
            log.warning("No plot: %s", e)
            return
        top = tk.Toplevel(self.root)
        top.title(f"Run {result.timestamp}")
        fig = make_figure(result.samples, result.params.points, result.params.duration)
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        NavigationToolbar2Tk(canvas, top).update()
        canvas.get_tk_widget().pack(fill="both", expand=True)
