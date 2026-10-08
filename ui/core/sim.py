"""Simulated boards, for running the GUI, the CLI and the tests without hardware.

SimHatLink answers the console commands a run uses and streams telemetry at
20 Hz while the output is on, from a crude cell model (a fixed overpotential
plus a series resistance). RE - WE is that overpotential plus the part of the
resistance between the reference and the working electrode, or full scale
with the reference left open. SimPrinterLink acts like Marlin: "ok" for each
command, moves that take time, M400 that waits for them, M114 and M115.
"""

from __future__ import annotations

import heapq
import itertools
import math
import random
import re
import threading
import time
from typing import Callable, List, Optional, Tuple

from .devices import Hat, Printer, Rig
from .link import Link


class _TimedLink(Link):
    """Lines queued with a release time; read_line waits for the next one."""

    def __init__(self, port: str):
        self.port = port
        self._queue: List[Tuple[float, int, str]] = []
        self._seq = itertools.count()
        self._cond = threading.Condition()
        self.closed = False
        self.sent: List[str] = []

    def _push(self, line: str, delay: float = 0.0) -> None:
        with self._cond:
            heapq.heappush(self._queue, (time.monotonic() + delay, next(self._seq), line))
            self._cond.notify_all()

    def _generate(self, now: float) -> Optional[str]:
        """Hook for lines produced on demand (telemetry)."""
        return None

    def _next_generated_at(self, now: float) -> Optional[float]:
        return None

    def read_line(self, timeout: float) -> Optional[str]:
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                now = time.monotonic()
                if self._queue and self._queue[0][0] <= now:
                    return heapq.heappop(self._queue)[2]
                generated = self._generate(now)
                if generated is not None:
                    return generated
                wake = [deadline]
                if self._queue:
                    wake.append(self._queue[0][0])
                upcoming = self._next_generated_at(now)
                if upcoming is not None:
                    wake.append(upcoming)
                wait = min(wake) - now
                if now >= deadline:
                    return None
                self._cond.wait(max(0.0, wait))

    def write_line(self, text: str) -> None:
        with self._cond:
            self.sent.append(text)
            self._handle(text.strip())
            self._cond.notify_all()

    def _handle(self, text: str) -> None:
        raise NotImplementedError

    def discard_input(self) -> None:
        with self._cond:
            now = time.monotonic()
            self._queue = [item for item in self._queue if item[0] > now]
            heapq.heapify(self._queue)

    def close(self) -> None:
        self.closed = True


class SimHatLink(_TimedLink):
    STEP_S = 0.05
    OVERPOTENTIAL_V = 1.2
    RESISTANCE_OHM = 40.0
    MAX_V = 30.0
    # RE - WE: the cathodic overpotential plus the uncompensated resistance.
    RE_OVERPOTENTIAL_V = 0.6
    RE_RESISTANCE_OHM = 5.0
    CELL_FULL_SCALE_V = 2.048

    def __init__(self, psu: bool = True, trip_after: Optional[float] = None,
                 formats: Tuple[int, ...] = (0, 1, 2, 3), reference_open: bool = False):
        super().__init__("sim:hat")
        self.psu = psu
        self.trip_after = trip_after
        # Telemetry formats the firmware knows; (0, 1, 2) is ECRIT_HAT before
        # format 3, () a sketch with no `t` at all.
        self.formats = formats
        self.reference_open = reference_open
        # Contact probe. `touching` says whether anode and cathode touch;
        # sim_rig wires it to the simulated printer's Z.
        self.touching: Callable[[], bool] = lambda: False
        self.probe_state = "idle"
        self.probe_started = 0.0
        self.probe_ended = 0.0
        self.active = False
        self.current_mode = False
        self.target_current = 0.0
        self.output_v = 0.5
        self.telemetry_format = 0
        self._on_since = 0.0
        self._next_emit = 0.0

    def _handle(self, text: str) -> None:
        parts = text.split()
        if not parts:
            return
        word, arg = parts[0].lower(), (float(parts[1]) if len(parts) > 1 and _is_number(parts[1]) else None)
        if word in ("c", "v"):
            if not self.psu:
                self._push("PSU not Connected")
                return
            if self.probe_state == "armed":
                self._push("Probe in progress. Send probe stop first.")
                return
            self.active = True
            self.current_mode = word == "c"
            if self.current_mode:
                self.target_current = arg if arg is not None else self.target_current
                self._push(f"Hold Current target = {self.target_current:.2f} mA")
            else:
                self.output_v = arg if arg is not None else self.output_v
                self._push(f"Hold Voltage target = {self.output_v:.2f} V")
            self._on_since = time.monotonic()
            self._next_emit = self._on_since + self.STEP_S
        elif word == "r":
            self.output_v = 0.5
            self._push("Reset")
        elif word == "f":
            if self.probe_state == "armed":
                self._probe_finish("aborted")
            self.active = False
            self._push("Turn off")
        elif word == "z":
            if self.active or self.probe_state == "armed":
                self._push("Cannot zero while active. Turn the output off first.")
                return
            self._push("current zero = 0.0123 mA")
            self._push("WE zero = 0.00001 A")
            self._push("Zero calibrated")
        elif word == "probe":
            self._handle_probe(parts[1].lower() if len(parts) > 1 else "")
        elif word == "t" and self.formats:
            if arg is not None:
                self.telemetry_format = int(arg) if int(arg) in self.formats else 0
            self._push(f"Telemetry format {self.telemetry_format}")
        elif word == "t":
            pass  # the older sketches ignore unknown commands
        elif word == "s":
            for line in ("--- status ---", "sim: simulated ECRIT-HAT",
                         "psu: " + ("connected" if self.psu else "PSU not Connected"),
                         "output: " + ("on" if self.active else "off")):
                self._push(line)
        elif word == "lim":
            self._push("interlocks: simulated")
        elif word in ("h", "help"):
            self._push("Commands: c v r f s t lim h (simulated)")
        else:
            self._push(f"Unknown command: {text}")

    def _handle_probe(self, sub: str) -> None:
        now = time.monotonic()
        if sub == "start":
            if self.active:
                self._push("Cannot probe while the output is active. Send f first.")
            elif not self.psu:
                self._push("PSU not Connected")
            else:
                self.probe_state = "armed"
                self.probe_started = now
                self._push(self._probe_line(now))
        elif sub == "stop":
            if self.probe_state == "armed":
                self._probe_finish("aborted")
            else:
                self.probe_state, self.probe_started = "idle", 0.0
                self._push(self._probe_line(now))
        elif sub in ("cfg", "set"):
            for line in ("--- probe settings ---", "volts = 1.000 V", "ilim = 10.000 mA", "thresh = 1.000 mA",
                         "debounce = 2 samples", "timeout = 60000 ms"):
                self._push(line)
        elif sub == "":
            if self.probe_state == "armed" and self.touching():
                self._probe_finish("contact")
            else:
                self._push(self._probe_line(now))
        else:
            self._push(f"Unknown probe command: {sub}")

    def _probe_finish(self, state: str) -> None:
        self.probe_state = state
        self.probe_ended = time.monotonic()
        self._push(self._probe_line(self.probe_ended))

    def _probe_line(self, now: float) -> str:
        current = 9.87 if self.probe_state == "contact" else random.uniform(-0.05, 0.05)
        end = now if self.probe_state == "armed" else self.probe_ended
        elapsed = int((end - self.probe_started) * 1000) if self.probe_started else 0
        extra = " ce_V=0.0421" if self.probe_state == "contact" else ""
        return f"PROBE state={self.probe_state} current_mA={current:.4f}{extra} elapsed_ms={elapsed}"

    def _cell(self) -> Tuple[float, float]:
        """(current_mA, PSU voltage) for the present setpoint."""
        if self.current_mode:
            current = self.target_current * (1 + random.uniform(-0.01, 0.01))
            volts = min(self.MAX_V, self.OVERPOTENTIAL_V + current / 1000 * self.RESISTANCE_OHM)
            self.output_v = volts
        else:
            volts = self.output_v
            current = max(0.0, (volts - self.OVERPOTENTIAL_V) / self.RESISTANCE_OHM * 1000)
            current *= 1 + random.uniform(-0.01, 0.01)
        return current, volts

    def _generate(self, now: float) -> Optional[str]:
        if self.probe_state == "armed" and self.touching():
            # The firmware's unsolicited contact line.
            self._probe_finish("contact")
            return None
        if not self.active or now < self._next_emit:
            return None
        self._next_emit += self.STEP_S
        if self.trip_after is not None and now - self._on_since >= self.trip_after:
            self.active = False
            self._push("Turn off")
            return "TRIP ocp at 99.000"
        current, volts = self._cell()
        readback = volts + random.uniform(-0.005, 0.005)
        row = f"{current:.4f},{volts:.3f},{readback:.3f}"
        if self.telemetry_format in (1, 3):
            if self.reference_open:
                cell = self.CELL_FULL_SCALE_V
            else:
                cell = self.RE_OVERPOTENTIAL_V + current / 1000 * self.RE_RESISTANCE_OHM
                cell = min(self.CELL_FULL_SCALE_V, cell + random.uniform(-0.0005, 0.0005))
            row += f",{cell:.5f}"
            if self.telemetry_format == 1:
                row += f",{volts / 7.667:.4f},{cell + current / 1000 * 0.008:.4f},0.0000,2.3000,CV"
        return row

    def _next_generated_at(self, now: float) -> Optional[float]:
        if self.probe_state == "armed":
            return now + 0.01  # check for contact every 10 ms
        return self._next_emit if self.active else None


class SimPrinterLink(_TimedLink):
    STEPS_PER_MM = {"X": 80, "Y": 80, "Z": 400}  # the rig's M92

    def __init__(self, speed_mm_s: float = 50.0, home_s: float = 2.0, quickstop_ok_s: float = 2.0):
        super().__init__("sim:printer")
        self.speed = speed_mm_s          # also the cap on any F
        self.feed: Optional[float] = None  # mm/s from the last F, if any
        self.home_s = home_s
        self.quickstop_ok_s = quickstop_ok_s
        # Like Marlin, M114 reports the planned position, not the live one.
        self.position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.segments: List[Tuple[float, float, dict, dict]] = []  # (t0, t1, from, to)
        self.absolute = True
        self.idle_at = 0.0  # when the last queued move finishes
        self.lcd = ""
        self.moves: List[Tuple[Optional[float], Optional[float], Optional[float]]] = []

    def live(self) -> dict:
        """Where the head is right now."""
        now = time.monotonic()
        for t0, t1, a, b in self.segments:
            if now < t0:
                return dict(a)
            if now < t1:
                f = (now - t0) / (t1 - t0)
                return {k: a[k] + (b[k] - a[k]) * f for k in a}
        return dict(self.position)

    def _handle(self, text: str) -> None:
        now = time.monotonic()
        start = max(now, self.idle_at)
        word = text.split()[0].upper() if text else ""
        if word in ("G0", "G1"):
            feed = re.search(r"F(-?[\d.]+)", text.upper())
            if feed:
                self.feed = float(feed.group(1)) / 60
            target = dict(self.position)
            given = {}
            for axis, value in re.findall(r"([XYZ])(-?[\d.]+)", text.upper()):
                value = float(value)
                target[axis] = value if self.absolute else target[axis] + value
                given[axis] = target[axis]
            if given:
                speed = min(self.feed, self.speed) if self.feed else self.speed
                distance = math.dist([self.position[a] for a in "XYZ"], [target[a] for a in "XYZ"])
                self.segments = [seg for seg in self.segments if seg[1] > now]
                self.segments.append((start, start + distance / speed, dict(self.position), dict(target)))
                self.position = target
                self.idle_at = start + distance / speed
                self.moves.append((given.get("X"), given.get("Y"), given.get("Z")))
            self._push("ok")
        elif word == "M410":
            self.position = self.live()
            self.segments = []
            self.idle_at = now
            self._push("ok", self.quickstop_ok_s)
        elif word == "G28":
            self.idle_at = start + self.home_s
            self.segments = [(start, self.idle_at, dict(self.position), {"X": 0.0, "Y": 0.0, "Z": 0.0})]
            self.position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
            self._push_busy(now, self.idle_at)
            self._push("ok", self.idle_at - now)
        elif word == "M400":
            self._push_busy(now, self.idle_at)
            self._push("ok", max(0.0, self.idle_at - now))
        elif word == "G90":
            self.absolute = True
            self._push("ok")
        elif word == "G91":
            self.absolute = False
            self._push("ok")
        elif word == "M114":
            p, live = self.position, self.live()
            counts = " ".join(f"{a}:{round(live[a] * self.STEPS_PER_MM[a])}" for a in "XYZ")
            self._push(f"X:{p['X']:.2f} Y:{p['Y']:.2f} Z:{p['Z']:.2f} E:0.00 Count {counts}")
            self._push("ok")
        elif word == "M115":
            self._push("FIRMWARE_NAME:Marlin 2.1.1.2 (simulated) MACHINE_TYPE:Electroplating Machine V1")
            self._push("ok")
        elif word == "M117":
            self.lcd = text[4:].strip()
            self._push("ok")
        elif word in ("M300", "M220"):
            self._push("ok")
        else:
            self._push(f'echo:Unknown command: "{text}"')
            self._push("ok")

    def _push_busy(self, now: float, until: float) -> None:
        t = 2.0
        while now + t < until:
            self._push("echo:busy: processing", t)
            t += 2.0


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def sim_rig(speed_mm_s: float = 50.0, home_s: float = 2.0, psu: bool = True,
            trip_after: Optional[float] = None, surface_z: Optional[float] = 45.0,
            quickstop_ok_s: float = 2.0, formats: Tuple[int, ...] = (0, 1, 2, 3),
            reference_open: bool = False) -> Rig:
    """Simulated boards. The anode touches the cathode at Z <= surface_z
    (never, if None)."""
    hat = SimHatLink(psu=psu, trip_after=trip_after, formats=formats, reference_open=reference_open)
    printer = SimPrinterLink(speed_mm_s=speed_mm_s, home_s=home_s, quickstop_ok_s=quickstop_ok_s)
    if surface_z is not None:
        hat.touching = lambda: printer.live()["Z"] <= surface_z + 1e-9
    return Rig(Hat(hat), Printer(printer))

