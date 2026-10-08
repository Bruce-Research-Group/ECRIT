"""Command-line front end: the same core as the GUI, without a display.

One-shot commands (status, hat, gcode, home, move, jog, run, plot) for
scripts and work over ssh, and `shell`, which mirrors the controller window
button for button and also reads commands from a pipe.

Run `./ecrit_cli.py -h` from the repository root, or `./ecrit_cli.py --sim ...`
to use simulated boards.
"""

from __future__ import annotations

import argparse
import cmd
import logging
import shlex
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .core.devices import DeviceError, Rig, connect, detect
from .core.link import list_ports
from .core.plating import PlatingRun, RunParams, RunResult, Sample, describe_reference
from .core.probe import BaselineProbe, ProbeError, ProbeSettings
from .core.session import AXES, Session
from .core.settings import REPO_ROOT, Config, Options

log = logging.getLogger("ecrit")

DEFAULT_OUT = REPO_ROOT / "experiment_logs"
EXIT_OK, EXIT_ERROR, EXIT_STOPPED = 0, 1, 2


# ---------------------------------------------------------------- helpers

def open_rig(args, options: Options) -> Rig:
    if args.sim:
        from .core.sim import sim_rig
        return sim_rig(speed_mm_s=args.sim_speed)
    return connect(options, hat_port=args.hat, printer_port=args.printer)


def open_session(args, config: Config, options: Options) -> Session:
    rig = open_rig(args, options)
    session = Session(rig, config)
    try:
        session.start()
    except Exception:
        rig.close()
        raise
    print(f"HAT on {rig.hat.port}, printer on {rig.printer.port}. Head at {format_position(session)}.")
    return session


def format_position(session: Session) -> str:
    return "  ".join(f"{a.upper()} {session.position[a]:g}" for a in AXES)


def parse_point(text: str) -> Tuple[float, float]:
    try:
        x, y = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected X,Y, got {text!r}")
    return x, y


def confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt + " [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


class Progress:
    """Prints run events: every state change, and a sample once a second."""

    def __init__(self, every: float = 1.0):
        self.every = every
        self._last = -1.0

    def __call__(self, kind: str, payload: object) -> None:
        if kind == "state":
            print(f"-- {payload}")
        elif kind == "output":
            print(f"   HAT: {payload}")
            self._last = -1.0
        elif kind == "sample":
            s: Sample = payload  # type: ignore[assignment]
            if s.t_point - self._last >= self.every:
                self._last = s.t_point
                ref = "" if s.we_vs_re_V is None else f"  WE-RE={describe_reference(s.we_vs_re_V)}"
                print(f"   t={s.t_point:6.1f} s  I={s.current_mA:9.3f} mA  "
                      f"set={s.target_V:7.3f} V  read={s.voltage_V:7.3f} V{ref}")


class ProbeProgress:
    """Prints baseline search events: state changes and every 10th step."""

    def __init__(self):
        self.polls = 0
        self.last_moving = 0.0

    def __call__(self, kind: str, payload: object) -> None:
        if kind == "state":
            print(f"-- {payload}")
        elif kind == "moving":
            now = time.monotonic()
            if now - self.last_moving >= 1.0:
                self.last_moving = now
                print(f"   Z ~{payload:g}")
        elif kind == "step":
            z, reading = payload  # type: ignore[misc]
            self.polls += 1
            if self.polls % 10 == 1 or reading.state != "armed":
                current = "-" if reading.current_mA is None else f"{reading.current_mA:.3f} mA"
                print(f"   Z {z:<8g} {reading.state:8} {current}")


def probe_baseline(session: Session, settings: ProbeSettings, ask: bool) -> int:
    """Run the baseline search with Ctrl-C as cancel. Returns an exit code."""
    z = session.position["z"]
    coarse = f"sweeping at {settings.speed:g} mm/s" if settings.speed else f"{settings.step:g} mm steps"
    print(f"Searching down from Z {z:g}, at most {settings.max_travel:g} mm, {coarse} then {settings.fine_step:g} mm "
          f"steps; the cell is driven at the HAT's probe voltage while searching.")
    if ask and not confirm("Start the baseline search?"):
        print("Not started (pass -y to skip this question).")
        return EXIT_STOPPED
    probe = BaselineProbe(session, settings, on_event=ProbeProgress())
    box: list = []

    def work():
        try:
            box.append(probe.run())
        except Exception as e:
            box.append(e)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        print("\nCancelling: probe off, head stays where it is.")
        probe.stop()
        worker.join()

    outcome = box[0]
    if isinstance(outcome, ProbeError) and str(outcome) == "cancelled":
        print("Cancelled.")
        return EXIT_STOPPED
    if isinstance(outcome, Exception):
        print(f"error: {outcome}")
        return EXIT_ERROR
    print(f"Baseline Z {outcome.z:g} (coarse pass stopped at {outcome.coarse_z:g}; {outcome.steps} moves, "
          f"{outcome.seconds:.1f} s). Head at {format_position(session)}.")
    return EXIT_OK


def run_plating(rig: Rig, params: RunParams, out: Path, plot: Optional[Path]) -> int:
    """Run in a worker thread so Ctrl-C can cancel it cleanly."""
    run = PlatingRun(rig, params, work_dir=out, on_event=Progress())
    box: List[RunResult] = []
    worker = threading.Thread(target=lambda: box.append(run.run()), daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        print("\nCancelling: output off, head stays where it is.")
        run.stop()
        worker.join()

    result = box[0]
    print(result.summary())
    print(f"CSV: {result.csv_path}\nLog: {result.log_path}")
    if plot and result.samples:
        from .core.plot import save_plot
        save_plot(plot, result.samples, params.points, params.duration)
        print(f"Plot: {plot}")
    if result.error:
        return EXIT_ERROR
    return EXIT_STOPPED if result.stopped else EXIT_OK


# ---------------------------------------------------------------- commands

def cmd_ports(args, config, options) -> int:
    ports = list_ports()
    for p in ports:
        marks = [name for name, saved in (("saved HAT", options.arduino_port), ("saved printer", options.printer_port))
                 if saved == p.device]
        print(str(p) + (f"  <- {', '.join(marks)}" if marks else ""))
    if not ports:
        print("No serial ports.")
    return EXIT_OK


def cmd_detect(args, config, options) -> int:
    found = detect()
    print(f"HAT:     {found.hat or 'not found'}")
    print(f"Printer: {found.printer or 'not found'}")
    if args.save and found.hat and found.printer:
        options.arduino_port, options.printer_port = found.hat, found.printer
        options.save()
        print(f"Saved to {options.path}")
    return EXIT_OK if found.hat and found.printer else EXIT_ERROR


def cmd_status(args, config, options) -> int:
    session = open_session(args, config, options)
    try:
        print(f"Printer: {session.rig.printer.identify() or '(no M115 firmware line)'}")
        for line in session.rig.hat.console("s"):
            print(line)
    finally:
        session.rig.close()
    return EXIT_OK


def cmd_hat(args, config, options) -> int:
    rig = open_rig(args, options)
    try:
        for line in rig.hat.console(" ".join(args.line), quiet=args.quiet, timeout=args.timeout):
            print(line)
    finally:
        rig.close()
    return EXIT_OK


def cmd_gcode(args, config, options) -> int:
    rig = open_rig(args, options)
    try:
        for line in rig.printer.send(" ".join(args.line), timeout=args.timeout):
            print(line)
        print("ok")
    finally:
        rig.close()
    return EXIT_OK


def cmd_home(args, config, options) -> int:
    session = open_session(args, config, options)
    try:
        session.home()
        session.rig.printer.wait_for_moves()
        print(f"Homed. Head at {format_position(session)}.")
    finally:
        session.rig.close()
    return EXIT_OK


def cmd_move(args, config, options) -> int:
    if args.x is None and args.y is None and args.z is None:
        raise SystemExit("move: give at least one of --x --y --z")
    session = open_session(args, config, options)
    try:
        session.move_to(x=args.x, y=args.y, z=args.z)
        session.rig.printer.wait_for_moves()
        print(f"Head at {format_position(session)}.")
    finally:
        session.rig.close()
    return EXIT_OK


def cmd_jog(args, config, options) -> int:
    session = open_session(args, config, options)
    try:
        session.jog(args.axis, args.mm)
        session.rig.printer.wait_for_moves()
        print(f"Head at {format_position(session)}.")
    finally:
        session.rig.close()
    return EXIT_OK


def probe_settings(args, config: Config) -> ProbeSettings:
    settings = ProbeSettings.from_config(config)
    for name in ("speed", "step", "fine_step", "max_travel", "lift"):
        value = getattr(args, name, None)
        if value is not None:
            setattr(settings, name, value)
    try:
        settings.check()
    except ValueError as e:
        raise SystemExit(f"baseline: {e}")
    return settings


def cmd_baseline(args, config, options) -> int:
    settings = probe_settings(args, config)
    session = open_session(args, config, options)
    try:
        return probe_baseline(session, settings, ask=not args.yes)
    finally:
        session.rig.close()


def cmd_run(args, config, options) -> int:
    current_mode = config.current_mode if args.current is None and args.voltage is None else args.current is not None
    params = RunParams(
        points=args.point,
        baseline_z=args.baseline,
        distance=config.diff_z if args.distance is None else args.distance,
        duration=config.duration if args.duration is None else args.duration,
        current_mode=current_mode,
        target_current=config.target_current if args.current is None else args.current,
        target_voltage=config.target_voltage if args.voltage is None else args.voltage,
        travel_z=config.travel_z if args.travel_z is None else args.travel_z,
        reference=config.reference_electrode if args.ref is None else args.ref,
    )
    try:
        params.check(config)
    except ValueError as e:
        raise SystemExit(f"run: {e}")
    print(params.describe())
    if not args.yes and not confirm("Start? This moves the head and turns the output on."):
        print("Not started (pass -y to skip this question).")
        return EXIT_STOPPED

    rig = open_rig(args, options)
    try:
        Session(rig, config).start()
        return run_plating(rig, params, args.out, args.plot)
    finally:
        rig.close()


def cmd_plot(args, config, options) -> int:
    from .core.plot import load_run, save_plot
    samples, points, duration = load_run(args.csv)
    if not samples:
        raise SystemExit(f"plot: no samples in {args.csv}")
    if duration is None:
        duration = max(s.t_point for s in samples)
    out = args.output or Path(args.csv).with_suffix(".png")
    save_plot(out, samples, points, duration)
    print(f"Plot: {out}")
    return EXIT_OK


def cmd_shell(args, config, options) -> int:
    session = open_session(args, config, options)
    shell = Shell(session, out=args.out)
    try:
        shell.cmdloop()
    finally:
        session.rig.close()
    return EXIT_ERROR if shell.failures else EXIT_OK


# ---------------------------------------------------------------- shell

class Shell(cmd.Cmd):
    """Mirrors the controller window. `help` lists the commands. Commands
    can come from a pipe; then the first error ends the session."""

    intro = "Type help for commands, quit to leave."

    def __init__(self, session: Session, out: Path):
        self.interactive = sys.stdin.isatty()
        super().__init__()
        self.use_rawinput = self.interactive
        self.prompt = "ecrit> " if self.interactive else ""
        if not self.interactive:
            self.intro = None
        self.session = session
        self.out = out
        self.step = 1.0
        self.failures = 0

    # -- plumbing

    def precmd(self, line: str) -> str:
        if not self.interactive and line.strip() and line != "EOF":
            print(f"> {line.strip()}")
        return line

    def onecmd(self, line: str) -> bool:
        failures = self.failures
        try:
            done = bool(super().onecmd(line))
        except (DeviceError, ValueError, IndexError) as e:
            self.failures += 1
            print(f"error: {e}")
            done = False
        if self.failures > failures and not self.interactive:
            # From a pipe, the first error ends the script, so a failed
            # `home` cannot be followed by moves to the wrong place.
            print("stopping: the commands are from a pipe")
            return True
        return done

    def emptyline(self) -> bool:
        return False

    def default(self, line: str) -> None:
        self.failures += 1
        print(f"error: unknown command {line.split()[0]!r} (try help)")

    def _float(self, text: str, what: str) -> float:
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"{what} has to be a number, got {text!r}")

    def _show_pos(self) -> None:
        print(format_position(self.session))

    # -- motion (the controller page)

    def do_pos(self, arg):
        """pos: print the head position as last commanded."""
        self._show_pos()

    def do_sync(self, arg):
        """sync: read the head position from the printer (M114)."""
        self.session.sync_position()
        self._show_pos()

    def do_home(self, arg):
        """home: home all axes (G28). Make sure nothing is in the way."""
        self.session.home()
        self._show_pos()

    def do_step(self, arg):
        """step [mm]: show or set the jog step (0.1, 1, 10, 100 in the GUI)."""
        if arg.strip():
            self.step = self._float(arg, "step")
        print(f"step {self.step:g} mm")

    def do_jog(self, arg):
        """jog <x|y|z> [+|-|mm]: move one axis by the step, or by mm if given.
        jog z +   up one step       jog x -0.1   left 0.1 mm"""
        parts = arg.split()
        if not parts or parts[0].lower() not in AXES:
            raise ValueError("usage: jog <x|y|z> [+|-|mm]")
        axis = parts[0].lower()
        amount = parts[1] if len(parts) > 1 else "+"
        if amount in ("+", "-"):
            mm = self.step if amount == "+" else -self.step
        else:
            mm = self._float(amount, "distance")
        self.session.jog(axis, mm)
        self._show_pos()

    def do_move(self, arg):
        """move [x=X] [y=Y] [z=Z]: absolute move within the machine limits."""
        target = {}
        for item in arg.split():
            key, _, value = item.partition("=")
            if key.lower() not in AXES or not value:
                raise ValueError("usage: move [x=X] [y=Y] [z=Z]")
            target[key.lower()] = self._float(value, key)
        if not target:
            raise ValueError("usage: move [x=X] [y=Y] [z=Z]")
        self.session.move_to(**target)
        self._show_pos()

    def do_wait(self, arg):
        """wait: block until queued moves finish (M400)."""
        self.session.rig.printer.wait_for_moves()
        print("moves done")

    def do_startpoint(self, arg):
        """startpoint: the GUI's "Go To Start Point" (config.json start_*)."""
        self.session.go_to_start_point()
        self._show_pos()

    def do_baseline(self, arg):
        """baseline [-y]: "Probe Baseline Height". Move down from here until the
        electrode touches the cathode; that Z becomes the surface height.
        Asks first unless -y (required when commands come from a pipe).
        Overrides for config.json's "probe" settings: speed= (mm/s, 0 steps instead)
        step= fine= max= lift= (mm), e.g. baseline -y max=20 speed=0.5
        baseline here: "Set Baseline Height", the head's Z becomes the baseline.
        baseline <z>: set the baseline height to a number."""
        words = arg.split()
        settings = ProbeSettings.from_config(self.session.config)
        names = {"speed": "speed", "step": "step", "fine": "fine_step", "max": "max_travel", "lift": "lift"}
        number = []
        for word in words:
            key, eq, value = word.partition("=")
            if eq:
                if key not in names:
                    raise ValueError(f"unknown setting {key!r}; use speed= step= fine= max= lift=")
                setattr(settings, names[key], self._float(value, key))
            elif word != "-y":
                number.append(word)
        if number == ["here"]:
            self.session.rig.printer.wait_for_moves()
            print(f"baseline Z {self.session.set_baseline():g}")
            return
        if number:
            print(f"baseline Z {self.session.set_baseline(self._float(number[0], 'baseline')):g}")
            return
        settings.check()
        ask = "-y" not in words
        if ask and not self.interactive:
            print("not started (use baseline -y in scripts)")
            return
        if probe_baseline(self.session, settings, ask) == EXIT_ERROR:
            self.failures += 1

    def do_point(self, arg):
        """point: "Set Geometric Area" at the head's X,Y."""
        if self.session.add_point():
            print(f"{len(self.session.points)} point(s) set")
        else:
            x, y = self.session.position["x"], self.session.position["y"]
            print(f"a point is already set at ({x:g}, {y:g})")

    def do_undo(self, arg):
        """undo: remove the last geometric area."""
        removed = self.session.undo_point()
        print(f"removed {removed}" if removed else "no points to remove")

    def do_delete(self, arg):
        """delete <n>: remove point n (numbered as in points)."""
        removed = self.session.remove_point(self._point_number(arg) - 1)
        print(f"removed ({removed[0]:g}, {removed[1]:g}), {len(self.session.points)} point(s) left")

    def do_reorder(self, arg):
        """reorder <n> <to>: move point n to place <to> in the run order."""
        words = arg.split()
        if len(words) != 2:
            raise ValueError("usage: reorder <n> <to>")
        self.session.move_point(self._point_number(words[0]) - 1, self._point_number(words[1]) - 1)
        self.do_points("")

    def _point_number(self, text: str) -> int:
        try:
            return int(text.strip())
        except ValueError:
            raise ValueError(f"not a point number: {text.strip()!r}") from None

    def do_points(self, arg):
        """points: list the geometric areas in run order, numbered from 1 as in the GUI."""
        for i, (x, y) in enumerate(self.session.points, 1):
            print(f"{i}: ({x:g}, {y:g})")
        if not self.session.points:
            print("no points set")

    # -- parameters (the parameter page)

    def do_mode(self, arg):
        """mode [current|voltage]: show or set constant current / voltage."""
        if arg.strip():
            word = arg.strip().lower()
            if word not in ("current", "voltage"):
                raise ValueError("usage: mode current|voltage")
            self.session.current_mode = word == "current"
        print("mode", "current" if self.session.current_mode else "voltage")

    def _param(self, arg, attr, label, unit):
        if arg.strip():
            setattr(self.session, attr, self._float(arg, label))
        print(f"{label} {getattr(self.session, attr):g} {unit}")

    def do_current(self, arg):
        """current [mA]: target current for current mode."""
        self._param(arg, "target_current", "current", "mA")

    def do_voltage(self, arg):
        """voltage [V]: target voltage for voltage mode."""
        self._param(arg, "target_voltage", "voltage", "V")

    def do_distance(self, arg):
        """distance [mm]: electrode height above the baseline while plating."""
        self._param(arg, "distance", "distance", "mm")

    def do_duration(self, arg):
        """duration [s]: plating time at each point."""
        self._param(arg, "duration", "duration", "s")

    def do_ref(self, arg):
        """ref [on|off]: record the reference electrode (3-electrode cell)."""
        if arg.strip():
            word = arg.strip().lower()
            if word not in ("on", "off"):
                raise ValueError("usage: ref on|off")
            self.session.reference = word == "on"
        print("reference electrode", "on" if self.session.reference else "off")

    def do_params(self, arg):
        """params: check and show what start would run."""
        print(self.session.run_params().describe())

    def do_start(self, arg):
        """start [-y] [plot=FILE]: run the plating. Asks first unless -y
        (required when commands come from a pipe)."""
        words = shlex.split(arg)
        plot = next((Path(w[5:]) for w in words if w.startswith("plot=")), None)
        params = self.session.run_params()
        print(params.describe())
        if "-y" not in words and not confirm("Start? This moves the head and turns the output on."):
            print("not started" + ("" if self.interactive else " (use start -y in scripts)"))
            return
        code = run_plating(self.session.rig, params, self.out, plot)
        if code == EXIT_ERROR:
            self.failures += 1
        self.session.sync_position()
        self._show_pos()

    # -- raw access

    def do_hat(self, arg):
        """hat <line>: send a console line to the HAT and print the reply."""
        for line in self.session.rig.hat.console(arg):
            print(line)

    def do_gcode(self, arg):
        """gcode <line>: send G-code and print the reply. The position the
        shell tracks is not updated; use sync afterwards if it moved."""
        for line in self.session.rig.printer.send(arg, timeout=60):
            print(line)
        print("ok")

    def do_quit(self, arg):
        """quit: leave (also exit, or end of input)."""
        return True

    do_exit = do_quit

    def do_EOF(self, arg):
        if self.interactive:
            print()
        return True


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ecrit_cli.py", description="ECRIT electroplating rig, command line.")
    p.add_argument("--sim", action="store_true", help="use simulated boards instead of serial ports")
    p.add_argument("--sim-speed", type=float, default=100.0, metavar="MM_S", help="simulated head speed (default 100)")
    p.add_argument("--hat", metavar="PORT", help="HAT serial port (default: options.json, else search)")
    p.add_argument("--printer", metavar="PORT", help="printer serial port (default: options.json, else search)")
    p.add_argument("-v", "--verbose", action="store_true", help="log serial traffic")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    s = sub.add_parser("ports", help="list serial ports (no I/O)")
    s.set_defaults(func=cmd_ports)

    s = sub.add_parser("detect", help="probe USB serial ports for the HAT and the printer")
    s.add_argument("--save", action="store_true", help="store what was found in options.json")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("status", help="printer firmware and HAT status (s)")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("hat", help="send one console line to the HAT, print the reply")
    s.add_argument("line", nargs="+")
    s.add_argument("--quiet", type=float, default=0.3, metavar="S", help="reply ends after this long without a line")
    s.add_argument("--timeout", type=float, default=3.0, metavar="S")
    s.set_defaults(func=cmd_hat)

    s = sub.add_parser("gcode", help="send one G-code line, wait for ok, print the reply")
    s.add_argument("line", nargs="+")
    s.add_argument("--timeout", type=float, default=10.0, metavar="S", help="inactivity timeout (busy lines reset it)")
    s.set_defaults(func=cmd_gcode)

    s = sub.add_parser("home", help="home all axes (G28)")
    s.set_defaults(func=cmd_home)

    s = sub.add_parser("move", help="absolute move, within the config.json limits")
    for axis in AXES:
        s.add_argument(f"--{axis}", type=float)
    s.set_defaults(func=cmd_move)

    s = sub.add_parser("jog", help="relative move of one axis, clamped to the limits")
    s.add_argument("axis", choices=AXES)
    s.add_argument("mm", type=float)
    s.set_defaults(func=cmd_jog)

    s = sub.add_parser("baseline", help="find the baseline height: step down until the electrodes touch",
                       description="Searches straight down from where the head is. Unset values come from "
                                   "config.json (\"probe\").")
    s.add_argument("--speed", type=float, metavar="MM_S", help="coarse sweep speed; 0 steps instead")
    s.add_argument("--step", type=float, metavar="MM", help="coarse step when --speed is 0")
    s.add_argument("--fine-step", type=float, metavar="MM", help="fine step, 0 skips the fine pass")
    s.add_argument("--max-travel", type=float, metavar="MM", help="give up after descending this far")
    s.add_argument("--lift", type=float, metavar="MM", help="rise this far after contact")
    s.add_argument("-y", "--yes", action="store_true", help="do not ask before starting")
    s.set_defaults(func=cmd_baseline)

    s = sub.add_parser("run", help="plate at one or more points",
                       description="Unset values come from config.json.")
    s.add_argument("--point", type=parse_point, action="append", required=True, metavar="X,Y",
                   help="a geometric area; repeat for several, plated in order")
    s.add_argument("--baseline", type=float, required=True, metavar="Z", help="surface height (Set Baseline Height)")
    s.add_argument("--distance", type=float, metavar="MM", help="height above the baseline while plating")
    s.add_argument("--duration", type=float, metavar="S", help="seconds at each point")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--current", type=float, metavar="MA", help="constant current, mA")
    mode.add_argument("--voltage", type=float, metavar="V", help="constant voltage, V")
    s.add_argument("--travel-z", type=float, metavar="Z")
    ref = s.add_mutually_exclusive_group()
    ref.add_argument("--ref", dest="ref", action="store_true", default=None,
                     help="record the reference electrode (WE vs RE column and plot panel)")
    ref.add_argument("--no-ref", dest="ref", action="store_false", help="two electrodes only")
    s.add_argument("--out", type=Path, default=DEFAULT_OUT, metavar="DIR", help="where the CSV and log go")
    s.add_argument("--plot", type=Path, metavar="FILE", help="also save the plot (PNG, PDF, SVG)")
    s.add_argument("-y", "--yes", action="store_true", help="do not ask before starting")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("plot", help="plot a saved run's CSV")
    s.add_argument("csv", type=Path)
    s.add_argument("-o", "--output", type=Path, metavar="FILE", help="default: the CSV's name with .png")
    s.set_defaults(func=cmd_plot)

    s = sub.add_parser("shell", help="interactive controller, mirrors the GUI (reads a pipe too)")
    s.add_argument("--out", type=Path, default=DEFAULT_OUT, metavar="DIR", help="where runs are saved")
    s.set_defaults(func=cmd_shell)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(message)s" if not args.verbose else "%(relativeCreated)7.0f %(message)s")
    config = Config.load()
    options = Options.load()
    try:
        return args.func(args, config, options)
    except DeviceError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_STOPPED


if __name__ == "__main__":
    sys.exit(main())
