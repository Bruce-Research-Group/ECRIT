"""The main window: the controller page, the parameter page, and the run.

Controller page: home and jog, set the baseline height, and add the points
to plate at, shown in a list and on a map.
Parameter page: pick constant current or voltage, then the setpoint,
time and distance, then start.
A run opens a live readout with a cancel button; when it ends the results are
saved and plotted.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

from ..core.plating import PlatingRun, RunParams, RunResult, Sample, describe_reference
from ..core.probe import BaselineProbe, ProbeError, ProbeSettings
from ..core.session import Session
from ..core.settings import Options
from . import theme
from .pointlist import PointList
from .pointmap import PointMap
from .tasks import TaskRunner

log = logging.getLogger(__name__)

STEP_SIZES = (("0.1", 0.1), ("1", 1.0), ("10", 10.0), ("100", 100.0))
# (current_mode, title, detail) for the mode cards on the parameter page.
MODES = ((True, "Constant Current", "Holds a set current (mA)"),
         (False, "Constant Voltage", "Holds a set voltage (V)"))


class ControllerWindow:
    def __init__(self, root: tk.Tk, session: Session, tasks: TaskRunner, options: Options, sim: bool = False):
        self.root = root
        self.title_suffix = " (simulated)" if sim else ""
        self.session = session
        self.tasks = tasks
        self.options = options
        self.run: Optional[PlatingRun] = None
        self.step = tk.DoubleVar(root, 1.0)
        # (what was done, the points before it), newest last, for Undo.
        self.points_history: List[Tuple[str, List[Tuple[float, float]]]] = []

        self.controller_frm: Optional[tk.Frame] = None
        self.param_frm: Optional[tk.Frame] = None
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
        root = self.root
        root.title("ECRIT Controller" + self.title_suffix)
        root.wm_minsize(width=900, height=560)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        frm = tk.Frame(root, bg=theme.BG, padx=24, pady=18)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.grid_columnconfigure(1, weight=1)
        frm.grid_rowconfigure(0, weight=1)
        self.controller_frm = frm
        left = tk.Frame(frm, bg=theme.BG)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        right = tk.Frame(frm, bg=theme.BG)
        right.grid(row=0, column=1, sticky="nsew")

        # 1: where the head is, and moving it.
        self._step_heading(left, 0, "1", "Move the Head")
        readout = tk.Frame(left, bg=theme.CARD, padx=14, pady=8)
        readout.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.axis_labels = {}
        for col, axis in enumerate(("x", "y", "z")):
            tk.Label(readout, text=axis.upper(), bg=theme.CARD, fg=theme.SUBTLE, font="Helvetica 11 bold") \
                .grid(row=0, column=2 * col, padx=(0 if col == 0 else 14, 6))
            value = tk.Label(readout, bg=theme.CARD, fg="white", font="Helvetica 16 bold", width=6, anchor="w")
            value.grid(row=0, column=2 * col + 1, sticky="w")
            self.axis_labels[axis] = value

        steps = tk.Frame(left, bg=theme.BG)
        steps.grid(row=2, column=0, sticky="w", pady=(0, 12))
        ttk.Label(steps, text="Step").grid(row=0, column=0, padx=(0, 10))
        for i, (label, value) in enumerate(STEP_SIZES):
            tk.Radiobutton(steps, text=label, value=value, variable=self.step, indicatoron=False, width=4,
                           font="Helvetica 11 bold", bg=theme.CARD, fg="white", selectcolor=theme.ACCENT,
                           activebackground=theme.CARD_LINE, activeforeground="white", relief="flat",
                           offrelief="flat", bd=0, highlightthickness=0, pady=5) \
                .grid(row=0, column=1 + i, padx=(0, 4))
        ttk.Label(steps, text="mm").grid(row=0, column=1 + len(STEP_SIZES), padx=(6, 0))

        # X/Y pad and Z pad. Y is flipped: the up arrow moves the bed away (-Y).
        pads = tk.Frame(left, bg=theme.BG)
        pads.grid(row=3, column=0, sticky="w", pady=(0, 12))
        xy = tk.Frame(pads, bg=theme.BG)
        xy.grid(row=0, column=0)
        self._jog_button(xy, "\u25B2", "y", -1).grid(row=0, column=1, padx=2, pady=2)
        self._jog_button(xy, "\u25C0", "x", -1).grid(row=1, column=0, padx=2, pady=2)
        self._pad_label(xy, "X/Y").grid(row=1, column=1)
        self._jog_button(xy, "\u25B6", "x", +1).grid(row=1, column=2, padx=2, pady=2)
        self._jog_button(xy, "\u25BC", "y", +1).grid(row=2, column=1, padx=2, pady=2)
        z = tk.Frame(pads, bg=theme.BG)
        z.grid(row=0, column=1, padx=(36, 0))
        self._jog_button(z, "\u25B2", "z", +1).grid(row=0, column=0, padx=2, pady=2)
        self._pad_label(z, "Z").grid(row=1, column=0)
        self._jog_button(z, "\u25BC", "z", -1).grid(row=2, column=0, padx=2, pady=2)

        moves = tk.Frame(left, bg=theme.BG)
        moves.grid(row=4, column=0, sticky="w", pady=(0, 20))
        theme.button(moves, "Home", self._home, width=8).grid(row=0, column=0, padx=(0, 6))
        theme.button(moves, "Go To Start Point", self._go_to_start_point).grid(row=0, column=1)

        # 2: the surface height.
        self._step_heading(left, 5, "2", "Baseline Height")
        self.baseline_label = tk.Label(left, bg=theme.BG, font="Helvetica 13 bold", anchor="w")
        self.baseline_label.grid(row=6, column=0, sticky="w", padx=(30, 0), pady=(0, 8))
        baseline = tk.Frame(left, bg=theme.BG)
        baseline.grid(row=7, column=0, sticky="w", padx=(30, 0))
        theme.button(baseline, "Probe Baseline Height", self._probe_baseline).grid(row=0, column=0, padx=(0, 6))
        theme.button(baseline, "Set Baseline Height", self._set_baseline).grid(row=0, column=1)
        tk.Label(left, text="Probe lowers the electrode until it touches the cathode.\n"
                            "Set takes the head's current Z.",
                 bg=theme.BG, fg=theme.SUBTLE, justify="left", font="Helvetica 10") \
            .grid(row=8, column=0, sticky="w", padx=(30, 0), pady=(6, 0))

        # 3: the points to plate at, in run order.
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        heading = tk.Frame(right, bg=theme.BG)
        heading.grid(row=0, column=0, sticky="ew")
        heading.grid_columnconfigure(1, weight=1)
        self._step_heading(heading, 0, "3", "Plating Points")
        self.points_label = tk.Label(heading, bg=theme.BG, fg=theme.SUBTLE)
        self.points_label.grid(row=0, column=1, sticky="e", pady=(0, 8))
        config = self.session.config
        self.point_map = PointMap(right, bed=(config.x_limit, config.y_limit),
                                  invert_x=config.map_invert_x, invert_y=config.map_invert_y)
        self.point_map.grid(row=1, column=0, sticky="nsew")

        self.point_list = PointList(right, on_delete=self._delete_point, on_move=self._move_point,
                                    on_select=self._show_map)
        self.point_list.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        point_buttons = tk.Frame(right, bg=theme.BG)
        point_buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        point_buttons.grid_columnconfigure(2, weight=1)
        self.set_point_btn = theme.button(point_buttons, "+ Add Point Here", self._add_point)
        self.set_point_btn.grid(row=0, column=0, padx=(0, 6))
        self.undo_btn = theme.button(point_buttons, "", self._undo_points, width=13)
        self.undo_btn.grid(row=0, column=1)
        tk.Label(point_buttons, text="Drag \u2261 to reorder, \u2715 to remove", bg=theme.BG, fg=theme.SUBTLE,
                 font="Helvetica 10").grid(row=0, column=2, sticky="e")

        tk.Frame(frm, height=1, bg=theme.CARD_LINE).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(18, 14))
        theme.accent_button(frm, "Next: Parameters \u2192", self._next) \
            .grid(row=2, column=0, columnspan=2, sticky="e", ipadx=10, ipady=4)
        self._refresh()

    def _jog_button(self, parent, text, axis, sign) -> tk.Button:
        return theme.button(parent, text, lambda: self._jog(axis, sign), width=3, font="Helvetica 14")

    @staticmethod
    def _pad_label(parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(parent, text=text, bg=theme.BG, fg=theme.SUBTLE, font="Helvetica 11 bold")

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

    def _probe_baseline(self) -> None:
        settings = ProbeSettings.from_config(self.session.config)
        z = self.session.position["z"]
        how = f"at {settings.speed:g} mm/s" if settings.speed else f"{settings.step:g} mm at a time"
        if not messagebox.askokcancel(
                title="Probe Baseline Height",
                message=f"The head will move down from Z {z:g} (at most {settings.max_travel:g} mm, "
                        f"{how}) until the electrode touches the cathode, "
                        f"then rise {settings.lift:g} mm.\n\nWhile searching, the cell is driven at the "
                        f"HAT's probe voltage (1 V, 10 mA limit by default). The cell should be dry.\n\n"
                        f"Start?"):
            return
        ProbeWindow(self, settings)

    # Marking goes through the device thread too, so it sees the position
    # after any jog still queued ahead of it.
    def _set_baseline(self) -> None:
        """The manual way: the head's current Z becomes the baseline."""
        self._device(self.session.set_baseline, lambda z: log.info("Baseline set by hand at Z %g", z))


    def _add_point(self) -> None:
        def work():
            before = list(self.session.points)
            return before if self.session.add_point() else None

        def done(before):
            if before is None:
                log.info("A point is already set at that position")
            else:
                self._remember_points("Add", before)
        self._device(work, done)

    # Deleting, reordering and undoing only touch the session's list, so they
    # run here rather than on the device thread.
    def _delete_point(self, index: int) -> None:
        before = list(self.session.points)
        log.info("Removed point %d %s", index + 1, self.session.remove_point(index))
        self._remember_points("Delete", before)
        self._refresh()

    def _move_point(self, index: int, to: int, first: bool) -> None:
        """One step of a drag in the list. The list has already moved the row."""
        if first:
            self._remember_points("Reorder", list(self.session.points))
        self.session.move_point(index, to)
        self._refresh()

    def _remember_points(self, action: str, before: List[Tuple[float, float]]) -> None:
        self.points_history.append((action, before))
        del self.points_history[:-50]

    def _undo_points(self) -> None:
        if self.points_history:
            action, before = self.points_history.pop()
            self.session.points[:] = before
            log.info("Undid %s", action.lower())
            self._refresh()

    def _show_map(self) -> None:
        pos = self.session.position
        self.point_map.show(self.session.points, (pos["x"], pos["y"]), self.point_list.selected())

    def _refresh(self) -> None:
        if self.controller_frm is None or not self.controller_frm.winfo_exists():
            return
        s = self.session
        for axis, label in self.axis_labels.items():
            label.config(text=f"{s.position[axis]:g}")
        if s.baseline_set:
            self.baseline_label.config(text=f"Baseline Z {s.baseline_z:g}", fg="white")
        else:
            self.baseline_label.config(text="Baseline not set", fg=theme.WARN)

        count = len(s.points)
        self.points_label.config(text=f"{count} point{'' if count == 1 else 's'}")
        self.point_list.set_points(s.points)
        if self.points_history:
            self.undo_btn.config(text=f"\u21A9 Undo {self.points_history[-1][0]}", state="normal")
        else:
            self.undo_btn.config(text="\u21A9 Undo", state="disabled")
        # Greyed out until a baseline is set, as a hint. Still clickable.
        self.set_point_btn.config(fg="white" if s.baseline_set or count else theme.MUTED)
        self._show_map()

    def _next(self) -> None:
        if not self.session.points:
            messagebox.showwarning(title="Wait!", message="Cannot Set Parameters Without Setting ALL Geometric Areas!")
            return
        self.controller_frm.destroy()
        self.controller_frm = None
        self.show_params()

    # ------------------------------------------------------------ parameter page

    def show_params(self) -> None:
        s = self.session
        self.root.title("ECRIT Plating Parameters" + self.title_suffix)
        self.root.wm_minsize(width=600, height=200)
        frm = tk.Frame(self.root, bg=theme.BG, padx=24, pady=18)
        frm.grid(row=0, column=0)
        frm.grid_columnconfigure(0, weight=1)
        self.param_frm = frm

        self._step_heading(frm, 0, "1", "Mode")
        cards = tk.Frame(frm, bg=theme.BG)
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        cards.grid_columnconfigure((0, 1), weight=1, uniform="mode")
        self.mode_cards = {}
        for col, (current_mode, title, detail) in enumerate(MODES):
            card = ModeCard(cards, title, detail, command=lambda m=current_mode: self._set_mode(m))
            card.grid(row=0, column=col, sticky="nsew", padx=(0, 10) if col == 0 else 0)
            self.mode_cards[current_mode] = card

        self._step_heading(frm, 2, "2", "Parameters")
        fields = tk.Frame(frm, bg=theme.BG)
        fields.grid(row=3, column=0, sticky="ew", padx=(30, 0))
        # Current and voltage share the first row and only the selected
        # mode's is shown, so switching back and forth keeps what was typed.
        rows = (("current", 0, "Current", s.target_current, "mA"),
                ("voltage", 0, "Voltage", s.target_voltage, "V"),
                ("duration", 1, "Time at each point", s.duration, "s"),
                ("distance", 2, "WE\u2013CE distance", s.distance, "mm"))
        self.inputs = {}
        self.input_vars = {}  # kept: Tk drops a variable once Python frees it
        self.hints = {}
        self.input_rows = {}
        for key, row, text, value, unit in rows:
            setpoint = key in ("current", "voltage")
            label = tk.Label(fields, text=text, bg=theme.BG, fg="white",
                             font=("Helvetica", 12, "bold") if setpoint else theme.FONT)
            label.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            var = tk.StringVar(frm, f"{value:g}")
            var.trace_add("write", lambda *_: self._update_hints())
            entry = ttk.Entry(fields, width=8, font=theme.FONT, textvariable=var)
            entry.grid(row=row, column=1, sticky="w", pady=4)
            unit_label = ttk.Label(fields, text=unit, width=3)
            unit_label.grid(row=row, column=2, sticky="w", padx=(6, 14))
            hint = tk.Label(fields, text="", bg=theme.BG, fg=theme.SUBTLE, anchor="w")
            hint.grid(row=row, column=3, sticky="w")
            self.inputs[key] = entry
            self.input_vars[key] = var
            self.hints[key] = hint
            self.input_rows[key] = (label, entry, unit_label, hint)

        self.reference_var = tk.BooleanVar(frm, s.reference)
        # A classic Checkbutton: the ttk one barely changes when ticked on this background.
        tk.Checkbutton(fields, text="Use Reference Electrode (3-electrode cell)", variable=self.reference_var,
                       command=self._set_reference, font=theme.FONT, bg=theme.BG, fg="white",
                       selectcolor=theme.BG, activebackground=theme.BG, activeforeground="white",
                       highlightthickness=0).grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))

        tk.Frame(frm, height=1, bg=theme.CARD_LINE).grid(row=4, column=0, sticky="ew", pady=(18, 14))
        buttons = tk.Frame(frm, bg=theme.BG)
        buttons.grid(row=5, column=0, sticky="ew")
        buttons.grid_columnconfigure(1, weight=1)
        self.back_btn = theme.button(buttons, "\u2190 Back", self._back, width=10, bg=theme.BACK,
                                     activebackground=theme.BACK)
        self.back_btn.grid(row=0, column=0, sticky="w", ipady=4)
        self.start_btn = theme.accent_button(buttons, "\u25B6 Start Electroplating", self._start_run)
        self.start_btn.grid(row=0, column=2, sticky="e", ipadx=10, ipady=4)
        self._apply_mode()

    @staticmethod
    def _step_heading(parent: tk.Frame, row: int, number: str, text: str) -> None:
        heading = tk.Frame(parent, bg=theme.BG)
        heading.grid(row=row, column=0, sticky="w", pady=(0, 8))
        tk.Label(heading, text=number, width=2, bg=theme.ACCENT, fg="white",
                 font="Helvetica 11 bold").grid(row=0, column=0)
        tk.Label(heading, text=text, bg=theme.BG, fg="white",
                 font="Helvetica 13 bold").grid(row=0, column=1, padx=(8, 0))

    def _set_reference(self) -> None:
        self.session.reference = self.reference_var.get()

    def _set_mode(self, current_mode: bool) -> None:
        self.session.current_mode = current_mode
        self._apply_mode()

    def _apply_mode(self) -> None:
        current = self.session.current_mode
        for mode, card in self.mode_cards.items():
            card.select(mode == current)
        shown, hidden = ("current", "voltage") if current else ("voltage", "current")
        for widget in self.input_rows[hidden]:
            widget.grid_remove()
        for widget in self.input_rows[shown]:
            widget.grid()
        self._update_hints()

    def _number(self, key: str) -> Optional[float]:
        try:
            return float(self.inputs[key].get().strip())
        except ValueError:
            return None

    def _update_hints(self) -> None:
        """What the numbers add up to, or which one is not a number."""
        s = self.session
        # None: not a number.
        hints = {key: None if self._number(key) is None else "" for key in self.hints}
        duration = self._number("duration")
        if duration is not None:
            n = len(s.points)
            hints["duration"] = f"{duration * n:g} s in total, {n} point{'' if n == 1 else 's'}"
        distance = self._number("distance")
        if distance is not None:
            baseline = (f"baseline {s.baseline_z:g}" if s.baseline_set
                        else f"baseline not set, Z {s.baseline_z:g} from config")
            hints["distance"] = f"plates at Z {s.baseline_z + distance:g} ({baseline})"
        for key, text in hints.items():
            self.hints[key].config(text="not a number" if text is None else text,
                                   fg=theme.WARN if text is None else theme.SUBTLE)

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
        self._open_run_window(params)
        self.run = PlatingRun(self.session.rig, params,
                              on_event=lambda kind, payload: self.tasks.post(lambda: self._on_run_event(kind, payload)))
        self.tasks.submit(self.run.run, self._run_finished, self._run_crashed)

    # ------------------------------------------------------------ the run

    def _open_run_window(self, params: RunParams) -> None:
        top = tk.Toplevel(self.root, bg=theme.BG)
        top.title("Electroplating Run" + self.title_suffix)
        top.transient(self.root)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self._cancel)
        frm = tk.Frame(top, bg=theme.BG, padx=22, pady=16)
        frm.grid(sticky="nsew")
        self.run_window = top
        self.run_points = len(params.points)
        self.run_duration = params.duration

        self.run_heading = tk.Label(frm, text="Starting", bg=theme.BG, fg="white", font="Helvetica 15 bold",
                                    anchor="w")
        self.run_heading.grid(row=0, column=0, columnspan=3, sticky="w")
        target = (f"constant current, {params.target_current:g} mA" if params.current_mode
                  else f"constant voltage, {params.target_voltage:g} V")
        tk.Label(frm, text=f"{self.run_points} point{'' if self.run_points == 1 else 's'}, "
                           f"{params.duration:g} s each, {target}",
                 bg=theme.BG, fg=theme.SUBTLE, anchor="w").grid(row=1, column=0, columnspan=3, sticky="w")
        self.run_state = tk.Label(frm, text="Starting...", bg=theme.BG, fg=theme.SUBTLE, anchor="w")
        self.run_state.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 12))

        tiles = [("current", "Current"), ("voltage", "Voltage"), ("target", "PSU setpoint")]
        if params.reference:
            tiles.append(("reference", "WE vs RE"))
        # One row of three, or two rows of two with the reference electrode.
        columns = 3 if len(tiles) == 3 else 2
        frm.grid_columnconfigure(tuple(range(columns)), weight=1, uniform="readout")
        self.run_labels = {}
        for i, (key, title) in enumerate(tiles):
            value = readout_tile(frm, title)
            column = i % columns
            value.master.grid(row=3 + i // columns, column=column, sticky="nsew", pady=(0, 8),
                              padx=(0, 8) if column < columns - 1 else 0)
            self.run_labels[key] = value

        progress = tk.Frame(frm, bg=theme.BG)
        progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        progress.grid_columnconfigure(0, weight=1)
        self.run_progress = ttk.Progressbar(progress, style="Run.Horizontal.TProgressbar", maximum=params.duration)
        self.run_progress.grid(row=0, column=0, sticky="ew")
        self.run_time = tk.Label(progress, text="", bg=theme.BG, fg=theme.SUBTLE, width=12, anchor="e")
        self.run_time.grid(row=0, column=1, sticky="e")

        tk.Frame(frm, height=1, bg=theme.CARD_LINE).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 12))
        self.cancel_btn = theme.button(frm, "\u25A0 Cancel Experiment", self._cancel, bg=theme.CANCEL,
                                       activebackground=theme.CANCEL, font="Helvetica 11 bold")
        self.cancel_btn.grid(row=7, column=0, columnspan=3, sticky="e", ipadx=10, ipady=4)

    def _cancel(self) -> None:
        if self.run is None:
            return
        self.cancel_btn.config(state="disabled", bg=theme.CANCELLED)
        self.run_state.config(text="Cancelling: output off, the head stays where it is.")
        self.run.stop()

    def _on_run_event(self, kind: str, payload) -> None:
        if self.run_window is None or not self.run_window.winfo_exists():
            return
        labels = self.run_labels
        if kind == "state":
            self.run_state.config(text=str(payload))
        elif kind == "point":
            i, x, y = payload
            self.run_heading.config(text=f"Point {i + 1} of {self.run_points}")
            self.run_state.config(text=f"Plating at X {x:g}, Y {y:g}")
            self.run_progress.config(value=0)
            self.run_time.config(text=f"{self.run_duration:.0f} s left")
        elif kind == "sample":
            s: Sample = payload
            labels["current"].config(text=f"{s.current_mA:.2f} mA")
            labels["voltage"].config(text=f"{s.voltage_V:.3f} V")
            labels["target"].config(text=f"{s.target_V:.3f} V")
            if "reference" in labels:
                labels["reference"].config(text=describe_reference(s.we_vs_re_V))
            self.run_progress.config(value=min(s.t_point, self.run_duration))
            self.run_time.config(text=f"{max(0, int(self.run_duration - s.t_point))} s left")

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
        top.title(f"Run Results {result.timestamp}" + self.title_suffix)
        fig = make_figure(result.samples, result.params.points, result.params.duration)
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        NavigationToolbar2Tk(canvas, top).update()
        canvas.get_tk_widget().pack(fill="both", expand=True)


def readout_tile(parent: tk.Misc, title: str) -> tk.Label:
    """A live value in a dark box with a small title above it. Returns the
    value label; grid its master (the box)."""
    tile = tk.Frame(parent, bg=theme.CARD, padx=14, pady=8)
    tk.Label(tile, text=title, bg=theme.CARD, fg=theme.SUBTLE, font="Helvetica 10 bold", anchor="w") \
        .grid(row=0, column=0, sticky="w")
    value = tk.Label(tile, text="-", bg=theme.CARD, fg="white", font="Helvetica 17 bold", anchor="w", width=9)
    value.grid(row=1, column=0, sticky="w")
    return value


class ModeCard(tk.Frame):
    """One of the two mode choices: a large clickable card, filled with the
    accent colour and marked with a dot when it is the selected one."""

    def __init__(self, parent: tk.Misc, title: str, detail: str, command):
        super().__init__(parent, cursor="hand2", highlightthickness=2, padx=14, pady=10)
        self.mark = tk.Label(self, font=("Helvetica", 16))
        self.mark.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 10))
        self.title = tk.Label(self, text=title, font=("Helvetica", 13, "bold"), anchor="w")
        self.title.grid(row=0, column=1, sticky="w")
        self.detail = tk.Label(self, text=detail, anchor="w", justify="left")
        self.detail.grid(row=1, column=1, sticky="w")
        for widget in (self, self.mark, self.title, self.detail):
            widget.bind("<Button-1>", lambda _event: command())

    def select(self, selected: bool) -> None:
        bg = theme.ACCENT if selected else theme.CARD
        line = theme.CARD_ON if selected else theme.CARD_LINE
        self.config(bg=bg, highlightbackground=line, highlightcolor=line)
        self.mark.config(text="\u25CF" if selected else "\u25CB", bg=bg, fg="white" if selected else theme.SUBTLE)
        self.title.config(bg=bg, fg="white" if selected else theme.SUBTLE)
        self.detail.config(bg=bg, fg="white" if selected else theme.MUTED)


class ProbeWindow:
    """Live readout of the baseline search, with a cancel button. Modal: the
    controller stays locked until the search ends."""

    def __init__(self, controller: ControllerWindow, settings: ProbeSettings):
        self.controller = controller
        top = tk.Toplevel(controller.root, bg=theme.BG)
        top.title("Probing Baseline Height" + controller.title_suffix)
        top.transient(controller.root)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self._cancel)
        frm = tk.Frame(top, bg=theme.BG, padx=22, pady=16)
        frm.grid()
        frm.grid_columnconfigure((0, 1), weight=1, uniform="readout")
        self.top = top
        tk.Label(frm, text="Searching for the surface", bg=theme.BG, fg="white", font="Helvetica 15 bold") \
            .grid(row=0, column=0, columnspan=2, sticky="w")
        self.state = tk.Label(frm, text="Starting...", bg=theme.BG, fg=theme.SUBTLE, anchor="w")
        self.state.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))
        z_tile = readout_tile(frm, "Head Z")
        z_tile.master.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        current_tile = readout_tile(frm, "Current")
        current_tile.master.grid(row=2, column=1, sticky="nsew")
        self.z, self.current = z_tile, current_tile
        tk.Frame(frm, height=1, bg=theme.CARD_LINE).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 12))
        self.cancel_btn = theme.button(frm, "\u25A0 Cancel", self._cancel, bg=theme.CANCEL,
                                       activebackground=theme.CANCEL, font="Helvetica 11 bold", width=10)
        self.cancel_btn.grid(row=4, column=0, columnspan=2, sticky="e", ipady=4)
        top.grab_set()

        tasks = controller.tasks
        self.probe = BaselineProbe(controller.session, settings,
                                   on_event=lambda kind, payload: tasks.post(lambda: self._on_event(kind, payload)))
        tasks.submit(self.probe.run, self._done, self._failed)

    def _cancel(self) -> None:
        self.cancel_btn.config(state="disabled", bg=theme.CANCELLED)
        self.state.config(text="Cancelling...")
        self.probe.stop()

    def _on_event(self, kind: str, payload) -> None:
        if not self.top.winfo_exists():
            return
        if kind == "state":
            self.state.config(text=str(payload))
        elif kind == "step":
            z, reading = payload
            self.z.config(text=f"{z:g}")
            self.current.config(text="-" if reading.current_mA is None else f"{reading.current_mA:.3f} mA")
            self.state.config(text=f"Probe: {reading.state}")
            self.controller._refresh()
        elif kind == "moving":
            self.z.config(text=f"~{payload:g}")
            self.current.config(text="moving")

    def _close(self) -> None:
        if self.top.winfo_exists():
            self.top.grab_release()
            self.top.destroy()
        self.controller._refresh()

    def _done(self, result) -> None:
        self._close()
        messagebox.showinfo(title="Baseline Height",
                            message=f"Contact at Z {result.z:g}, found in {result.seconds:.0f} s. "
                                    f"That is now the baseline height.")

    def _failed(self, e: Exception) -> None:
        self._close()
        if isinstance(e, ProbeError) and str(e) == "cancelled":
            log.info("Baseline search cancelled")
            return
        messagebox.showerror(title="Baseline Height", message=f"No baseline found: {e}")
