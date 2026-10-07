"""Simulated boards, for running the GUI, the CLI and the tests without hardware.

SimHatLink answers the console commands a run uses and streams telemetry at
20 Hz while the output is on, from a crude cell model (a fixed overpotential
plus a series resistance). SimPrinterLink acts like Marlin: "ok" for each
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
from typing import List, Optional, Tuple

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

    def __init__(self, psu: bool = True, trip_after: Optional[float] = None):
        super().__init__("sim:hat")
        self.psu = psu
        self.trip_after = trip_after
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
            self.active = False
            self._push("Turn off")
        elif word == "t":
            if arg is not None:
                self.telemetry_format = int(arg) if 0 <= arg <= 2 else 0
            self._push(f"Telemetry format {self.telemetry_format}")
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
        if not self.active or now < self._next_emit:
            return None
        self._next_emit += self.STEP_S
        if self.trip_after is not None and now - self._on_since >= self.trip_after:
            self.active = False
            self._push("Turn off")
            return "TRIP ocp at 99.000"
        current, volts = self._cell()
        readback = volts + random.uniform(-0.005, 0.005)
        return f"{current:.4f},{volts:.3f},{readback:.3f}"

    def _next_generated_at(self, now: float) -> Optional[float]:
        return self._next_emit if self.active else None


class SimPrinterLink(_TimedLink):
    def __init__(self, speed_mm_s: float = 50.0, home_s: float = 2.0):
        super().__init__("sim:printer")
        self.speed = speed_mm_s
        self.home_s = home_s
        self.position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.absolute = True
        self.idle_at = 0.0  # when the last queued move finishes
        self.lcd = ""
        self.moves: List[Tuple[Optional[float], Optional[float], Optional[float]]] = []

    def _handle(self, text: str) -> None:
        now = time.monotonic()
        start = max(now, self.idle_at)
        word = text.split()[0].upper() if text else ""
        if word in ("G0", "G1"):
            target = dict(self.position)
            given = {}
            for axis, value in re.findall(r"([XYZ])(-?[\d.]+)", text.upper()):
                value = float(value)
                target[axis] = value if self.absolute else target[axis] + value
                given[axis] = target[axis]
            distance = math.dist([self.position[a] for a in "XYZ"], [target[a] for a in "XYZ"])
            self.position = target
            self.idle_at = start + distance / self.speed
            self.moves.append((given.get("X"), given.get("Y"), given.get("Z")))
            self._push("ok")
        elif word == "G28":
            self.idle_at = start + self.home_s
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
            p = self.position
            self._push(f"X:{p['X']:.2f} Y:{p['Y']:.2f} Z:{p['Z']:.2f} E:0.00 Count X:0 Y:0 Z:0")
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
            trip_after: Optional[float] = None) -> Rig:
    return Rig(Hat(SimHatLink(psu=psu, trip_after=trip_after)),
               Printer(SimPrinterLink(speed_mm_s=speed_mm_s, home_s=home_s)))

