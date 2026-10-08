"""One plating run: visit each point, plate for a fixed time, log everything.

The sequence (unchanged from the original UI):
  1. r to the HAT, G90 to the printer
  2. up to the travel height, then down to plating height + 2 mm
  3. for each point: move over it, drop to plating height, start the output
     (c or v), record telemetry for `duration` seconds, f, rise 2 mm
  4. back up to the travel height

A HAT "Turn off" (interlock trip) or a cancel stops the run where it is: the
output goes off and the head is not moved again.

Two files are written as the run goes, named after its start time:
  log_<stamp>.txt  settings, then every raw telemetry row with its time
  log_<stamp>.csv  Current, Target Voltage, Actual Voltage, Time Individual,
                   Time Accumulative; an empty row starts each point

With the reference electrode on, the HAT also reports RE - WE, and the CSV
gets a sixth column, Potential WE vs RE: the working electrode's potential
against the reference (V), the usual electrochemical sign, so RE - WE negated.
Without it the CSV is exactly the five columns above.
"""

from __future__ import annotations

import csv
import logging
import math
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .devices import CELL_FULL_SCALE_V, DeviceError, Rig, parse_cell_potential, parse_telemetry
from .settings import Config

log = logging.getLogger(__name__)

CSV_COLUMNS = ("Current", "Target Voltage", "Actual Voltage", "Time Individual", "Time Accumulative")
REFERENCE_COLUMN = "Potential WE vs RE"


def csv_columns(reference: bool) -> Tuple[str, ...]:
    return CSV_COLUMNS + (REFERENCE_COLUMN,) if reference else CSV_COLUMNS


def describe_reference(we_vs_re: Optional[float]) -> str:
    """Live readout of WE vs RE, e.g. "-0.8123 V". A reading at full scale
    is what an open reference input gives, so say so."""
    if we_vs_re is None or math.isnan(we_vs_re):
        return "no reading"
    text = f"{we_vs_re:.4f} V"
    if abs(we_vs_re) >= CELL_FULL_SCALE_V - 0.005:
        text += " (full scale: is the RE connected?)"
    return text


@dataclass
class RunParams:
    points: List[Tuple[float, float]]
    baseline_z: float      # surface height, mm
    distance: float        # electrode height above the surface while plating, mm
    duration: float        # seconds at each point
    current_mode: bool     # True: constant current, False: constant voltage
    target_current: float  # mA
    target_voltage: float  # V
    travel_z: float        # mm
    lift: float = 2.0      # mm above plating height between points
    reference: bool = False  # record the reference electrode (3-electrode cell)

    @property
    def plate_z(self) -> float:
        return self.baseline_z + self.distance

    @property
    def target(self) -> float:
        return self.target_current if self.current_mode else self.target_voltage

    def describe(self) -> str:
        unit = "mA constant current" if self.current_mode else "V constant voltage"
        points = ", ".join(f"({x:g}, {y:g})" for x, y in self.points)
        return (f"{len(self.points)} point(s): {points}\n"
                f"{self.target:g} {unit} for {self.duration:g} s at each\n"
                f"plating Z {self.plate_z:g} (baseline {self.baseline_z:g} + {self.distance:g}), "
                f"travel Z {self.travel_z:g}\n"
                f"reference electrode {'on' if self.reference else 'off'}")

    def check(self, config: Config) -> None:
        problems = []
        numbers = [self.baseline_z, self.distance, self.duration, self.target, self.travel_z]
        numbers += [v for point in self.points for v in point]
        if not all(math.isfinite(v) for v in numbers):
            problems.append("Every value has to be a number.")
        if not self.points:
            problems.append("Set at least one geometric area first.")
        if not self.duration > 0:
            problems.append("The duration has to be more than 0 s.")
        for name, z in (("Plating height", self.plate_z), ("Travel height", self.travel_z)):
            if not 0 <= z <= config.z_limit - (self.lift if name == "Plating height" else 0):
                problems.append(f"{name} {z:g} mm is outside the Z limit.")
        for x, y in self.points:
            if not (0 <= x <= config.x_limit and 0 <= y <= config.y_limit):
                problems.append(f"Point ({x:g}, {y:g}) is outside the X/Y limits.")
        if problems:
            raise ValueError("\n".join(problems))


@dataclass
class Sample:
    point: int          # index into RunParams.points
    current_mA: float
    target_V: float     # the PSU setpoint
    voltage_V: float    # measured at the anode (CN1); PSU readback on older firmware
    t_point: float      # seconds since this point's output went on
    t_total: float      # t_point + point * duration
    # Working electrode vs reference (V), only with the reference electrode on.
    # NaN when the HAT had no reading.
    we_vs_re_V: Optional[float] = None


@dataclass
class RunResult:
    params: RunParams
    timestamp: str
    log_path: Path
    csv_path: Path
    samples: List[Sample] = field(default_factory=list)
    points_done: int = 0
    stopped: Optional[str] = None  # why it ended early, e.g. "cancelled"
    error: Optional[str] = None

    @property
    def completed(self) -> bool:
        return self.stopped is None and self.error is None

    def summary(self) -> str:
        if self.error:
            outcome = f"failed: {self.error}"
        elif self.stopped:
            outcome = f"stopped: {self.stopped}"
        else:
            outcome = "completed"
        return (f"Run {self.timestamp} {outcome}. {self.points_done}/{len(self.params.points)} point(s), "
                f"{len(self.samples)} sample(s).")

    def move_to(self, directory: Path) -> None:
        """Move both files into `directory`, keeping their names."""
        self.save_as(Path(directory) / self.csv_path.name)

    def save_as(self, csv_path: Path) -> None:
        """Move the CSV to `csv_path` and the log next to it (same name, .txt)."""
        csv_path = Path(csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        moves = [("csv_path", csv_path), ("log_path", csv_path.with_suffix(".txt"))]
        for attr, target in moves:
            source = getattr(self, attr)
            if target.resolve() != source.resolve() and target.exists():
                raise FileExistsError(f"{target} already exists")
        for attr, target in moves:
            source = getattr(self, attr)
            if target.resolve() != source.resolve():
                shutil.move(str(source), str(target))
                setattr(self, attr, target)


class _Stop(Exception):
    pass


# on_event(kind, payload):
#   "state"    str       what the run is doing (also shown on the printer LCD)
#   "point"    (i, x, y) arrived at point i
#   "output"   str       the HAT's confirmation that the output is on
#   "sample"   Sample
#   "finished" RunResult
EventHandler = Callable[[str, object], None]


class PlatingRun:
    def __init__(self, rig: Rig, params: RunParams, work_dir: Optional[Path] = None,
                 on_event: Optional[EventHandler] = None):
        self.rig = rig
        self.params = params
        self.work_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir())
        self.on_event = on_event
        self._stop = threading.Event()

    def stop(self) -> None:
        """Cancel from any thread. The output goes off immediately."""
        self._stop.set()
        try:
            self.rig.hat.send_off()
        except Exception as e:
            log.warning("Could not send f to the HAT: %s", e)

    def run(self) -> RunResult:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        result = RunResult(self.params, stamp,
                           log_path=self.work_dir / f"log_{stamp}.txt",
                           csv_path=self.work_dir / f"log_{stamp}.csv")

        with open(result.log_path, "w") as log_file, open(result.csv_path, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            columns = csv_columns(self.params.reference)
            writer.writerow(columns)
            self._write_header(log_file)
            try:
                self._sequence(result, log_file, writer, csv_file, len(columns))
            except _Stop as e:
                result.stopped = str(e)
            except DeviceError as e:
                log.error("Run failed: %s", e)
                result.error = str(e)
            except Exception as e:
                log.exception("Run failed")
                result.error = str(e) or type(e).__name__
            finally:
                self._shutdown()

        log.info("%s", result.summary())
        self._emit("finished", result)
        return result

    # ------------------------------------------------------------ internals

    def _write_header(self, f) -> None:
        p = self.params
        f.write(f"Starting Time {time.time()}\n")
        f.write(f"current_mode {p.current_mode}\n")
        f.write(f"target_current {p.target_current}\n")
        f.write(f"target_voltage {p.target_voltage}\n")
        f.write(f"duration {p.duration}s\n")
        f.write(f"diff_z {p.distance}mm\n")
        f.write(f"points {len(p.points)}\n")
        f.write(f"reference_electrode {p.reference}\n")
        f.write("====================================\n")

    def _sequence(self, result: RunResult, log_file, writer, csv_file, width: int) -> None:
        p = self.params
        hat, printer = self.rig.hat, self.rig.printer

        hat.reset()
        if p.reference:
            hat.use_reference_telemetry()
        else:
            hat.use_host_telemetry()
        printer.absolute_mode()

        self._state("To travel height")
        self._move(z=p.travel_z)
        self._state("To starting height")
        self._move(z=p.plate_z + p.lift)

        for i, (x, y) in enumerate(p.points):
            self._check_stop()
            writer.writerow([""] * width)
            label = f"x: {x:.3f}, y: {y:.3f}"
            log_file.write("\n" + label + "\n")
            self._state(label)
            self._move(x=x, y=y)
            self._move(z=p.plate_z)
            self._check_stop()
            self._emit("point", (i, x, y))

            self._emit("output", hat.start_output(p.current_mode, p.target))
            try:
                ended = self._plate(i, result, log_file, writer)
            finally:
                hat.output_off()
                log_file.flush()
                csv_file.flush()
            result.points_done = i + 1
            if ended:
                raise _Stop(ended)

            time.sleep(0.5)
            self._move(z=p.plate_z + p.lift)

        self._move(z=p.travel_z)

    def _plate(self, index: int, result: RunResult, log_file, writer) -> Optional[str]:
        """Record telemetry for one point. Returns why it ended early, or None."""
        duration = self.params.duration
        trip = None
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= duration:
                return None
            if self._stop.is_set():
                return "cancelled"
            line = self.rig.hat.read_line(min(0.2, duration - elapsed))
            if line is None:
                continue
            if line == "Turn off":
                if self._stop.is_set():
                    return "cancelled"
                return trip or "the HAT turned the output off"
            values = parse_telemetry(line)
            if values is None:
                if line.startswith("TRIP"):
                    trip = "HAT " + line
                    log.warning("HAT: %s", line)
                else:
                    log.info("HAT: %s", line)
                continue
            t = time.monotonic() - start
            log_file.write(f"{line},{t}\n")
            sample = Sample(index, values[0], values[1], values[2], t, t + index * duration)
            row = [sample.current_mA, sample.target_V, sample.voltage_V, sample.t_point, sample.t_total]
            if self.params.reference:
                cell = parse_cell_potential(line)
                sample.we_vs_re_V = math.nan if cell is None else -cell
                row.append(sample.we_vs_re_V)
            writer.writerow(row)
            result.samples.append(sample)
            self._emit("sample", sample)

    def _move(self, x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None) -> None:
        self.rig.printer.move(x=x, y=y, z=z)
        self.rig.printer.wait_for_moves()
        self._check_stop()

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise _Stop("cancelled")

    def _state(self, text: str) -> None:
        log.info("%s", text)
        self._emit("state", text)
        self.rig.printer.message(text)

    def _shutdown(self) -> None:
        try:
            self.rig.hat.send_off()
        except Exception as e:
            log.warning("Could not send f to the HAT: %s", e)
        if self.params.reference:
            # Leave the HAT on the plain format, as a board fresh from reset is.
            try:
                self.rig.hat.use_host_telemetry()
            except Exception as e:
                log.warning("Could not reset the HAT's telemetry format: %s", e)
        try:
            self.rig.printer.message("Done")
        except Exception as e:
            log.warning("Could not reach the printer: %s", e)

    def _emit(self, kind: str, payload: object) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(kind, payload)
        except Exception:
            log.exception("Run event handler failed")
