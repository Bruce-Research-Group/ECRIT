"""Find the baseline (surface) height by touching the anode to the cathode.

Uses the ECRIT-HAT contact probe (ECRIT_HAT/CALIBRATION.md, "Mechanical
zero"). `probe start` drives the cell at a low voltage behind a small current
limit; when current flows the firmware switches the output off itself, prints
`PROBE state=contact ...` and latches that state for later polls.

Sequence:
  1. z           capture the current zero, so the 1 mA threshold means something
  2. coarse pass sweep down at `speed` mm/s and quickstop (M410) on the
                 contact line; or, with speed 0, step down `step` mm at a time
  3. fine pass   back off `backoff` mm, re-arm, step down `fine_step` mm at a
                 time, polling while the head stands still
  4. lift        rise `lift` mm so the electrode does not rest on the cathode
The baseline is the first Z at which the fine pass saw contact.

The sweep relies on M410 acting at once. This Marlin has no emergency parser,
but G1 does not block the command queue (it is acknowledged as soon as it is
planned), so an M410 sent mid-move is executed straight away; measured on the
rig, the head stops where it is and M114 reports the stopped position. The
"ok" for M410 takes about 2 s. No more than ~1.5 `segment`s are ever planned
ahead of the head, so overtravel stays bounded even if the stop failed, and
the sweep checks that the head really stood still afterwards.

G1 F is modal in Marlin, so the sweep's slow feedrate is replaced by
config.travel_feedrate when it ends.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, fields
from typing import Callable, Optional, Tuple

from .devices import ProbeReading, parse_probe_line
from .session import Session
from .settings import Config

log = logging.getLogger(__name__)


class ProbeError(RuntimeError):
    pass


@dataclass
class ProbeSettings:
    speed: float = 1.0        # mm/s for the coarse sweep; 0 steps by `step` instead
    segment: float = 2.0      # mm per sweep move, the most it can overtravel if M410 failed
    step: float = 0.1         # mm per step on a stepped coarse pass
    fine_step: float = 0.02   # mm per step on the fine pass; 0 skips it
    backoff: float = 0.5      # mm to rise above the coarse stop before the fine pass
    lift: float = 1.0         # mm to rise once the baseline is found
    max_travel: float = 60.0  # mm to descend before giving up
    settle: float = 0.15      # s to stand still before each poll (firmware debounce is 2 x 50 ms)
    feedrate: float = 1500.0  # mm/min to leave the printer at afterwards

    @classmethod
    def from_config(cls, config: Config) -> "ProbeSettings":
        """Defaults, overridden by config.json's "probe" object; the feedrate
        comes from travel_feedrate."""
        known = {f.name for f in fields(cls)} - {"feedrate"}
        unknown = sorted(set(config.probe) - known)
        if unknown:
            log.warning('config.json: unknown "probe" setting(s) %s', ", ".join(unknown))
        values = {k: float(v) for k, v in config.probe.items() if k in known}
        return cls(feedrate=config.travel_feedrate, **values)

    def check(self) -> None:
        if not 0 <= self.speed <= 5:
            raise ValueError("The probe speed has to be between 0 (stepping) and 5 mm/s.")
        if self.speed and not 0 < self.segment <= 5:
            raise ValueError("The sweep segment has to be more than 0 and at most 5 mm.")
        if not 0 < self.step <= 1:
            raise ValueError("The probe step has to be more than 0 and at most 1 mm.")
        if not 0 <= self.fine_step <= self.step:
            raise ValueError("The fine step has to be between 0 and the probe step.")
        if self.fine_step and self.backoff <= self.fine_step:
            raise ValueError("The backoff has to be larger than the fine step.")
        if self.max_travel <= 0 or self.lift < 0 or self.settle < 0 or self.feedrate <= 0:
            raise ValueError("Max travel and feedrate have to be positive; lift and settle cannot be negative.")


@dataclass
class BaselineResult:
    z: float                     # the baseline: first Z with contact on the last pass
    coarse_z: float              # where the coarse pass stopped after contact
    current_mA: Optional[float]  # current the firmware saw at contact
    steps: int                   # moves made while searching
    seconds: float = 0.0         # from start to lift-off


# on_event(kind, payload):
#   "state"   str                  what it is doing
#   "step"    (z, ProbeReading)    after each poll while stepping
#   "moving"  z                    estimated Z during a sweep, a few times a second
EventHandler = Callable[[str, object], None]


class BaselineProbe:
    def __init__(self, session: Session, settings: Optional[ProbeSettings] = None,
                 on_event: Optional[EventHandler] = None):
        self.session = session
        self.settings = settings or ProbeSettings.from_config(session.config)
        self.on_event = on_event
        self._stop = threading.Event()
        self.steps = 0

    def stop(self) -> None:
        """Cancel from any thread. The probe output goes off immediately; a
        sweep in progress is stopped at its next check (within ~50 ms)."""
        self._stop.set()
        try:
            self.session.rig.hat.send_off()
        except Exception as e:
            log.warning("Could not send f to the HAT: %s", e)

    def run(self) -> BaselineResult:
        """Search from the current Z. Sets the session's baseline on success.
        Raises ProbeError (no contact, cancelled) or DeviceError."""
        s = self.settings
        s.check()
        hat, printer = self.session.rig.hat, self.session.rig.printer
        started = time.monotonic()
        # A jog or move may still be under way; the search starts from rest.
        printer.wait_for_moves()
        start_z = self.session.position["z"]
        lowest = max(0.0, start_z - s.max_travel)

        self._state("Capturing the current zero")
        hat.zero_current()
        # The firmware gives up after its own timeout (60 s by default), which
        # a long descent can exceed. Budget for the full travel at either rate.
        per_mm = max(1 / s.speed if s.speed else 0, (s.settle + 0.25) / s.step)
        budget_ms = int((s.max_travel * per_mm + 30) * 1000)
        hat.console(f"probe set timeout {budget_ms}", quiet=0.2, timeout=1.0)

        try:
            if s.speed:
                self._state(f"Sweeping down from Z {start_z:g} at {s.speed:g} mm/s")
                coarse_z, reading = self._sweep(lowest)
            else:
                self._state(f"Searching down from Z {start_z:g} in {s.step:g} mm steps")
                coarse_z, reading = self._descend(s.step, lowest)
            z = coarse_z
            if s.fine_step:
                z, reading = self._fine_pass(coarse_z)
        except BaseException:
            try:
                hat.send_off()
            except Exception as e:
                log.warning("Could not send f to the HAT: %s", e)
            raise
        finally:
            if s.speed:
                self._restore_feedrate()

        self.session.set_baseline(z)
        if s.lift:
            self._state("Lifting off")
            self.session.move_to(z=min(self.session.config.z_limit, round(z + s.lift, 3)))
            printer.wait_for_moves()
        result = BaselineResult(z=z, coarse_z=coarse_z, current_mA=reading.current_mA, steps=self.steps,
                                seconds=time.monotonic() - started)
        log.info("Baseline Z %g (coarse stop %g, %d moves, %.1f s)", z, coarse_z, self.steps, result.seconds)
        return result

    # ------------------------------------------------------------ coarse: sweep

    def _sweep(self, lowest: float) -> Tuple[float, ProbeReading]:
        """Move down continuously and quickstop on contact. Returns the Z the
        head stopped at, which is a little below the surface.

        The descent is a chain of `segment` mm moves. The next one is queued
        while the head is still on the current one, so it never stops in
        between; at most about 1.5 segments are planned ahead of the head,
        which bounds the overtravel if M410 ever failed."""
        s = self.settings
        hat, printer = self.session.rig.hat, self.session.rig.printer
        self._arm()

        # Already touching? Find out before moving.
        time.sleep(s.settle)
        reading = hat.probe()
        z0 = self.session.position["z"]
        self._emit("step", (z0, reading))
        if reading.state == "contact":
            return z0, reading
        self._expect_armed(reading, z0)
        if z0 <= lowest + 1e-9:
            hat.probe("probe stop")
            raise ProbeError(f"No contact down to Z {lowest:g}. Is the cell connected?")

        feedrate = s.speed * 60
        queued = z0          # lowest Z sent to the printer so far
        started = None       # when the first move was sent
        next_poll = next_report = 0.0
        contact = None
        try:
            while True:
                self._check_stop()
                now = time.monotonic()
                # Where the head should be. Acceleration and Marlin's start
                # delay keep the real head a little behind this, so moves get
                # queued early rather than late.
                estimate = z0 if started is None else max(lowest, z0 - (now - started) * s.speed)
                if queued > lowest + 1e-9 and estimate - queued < s.segment / 2:
                    queued = round(max(lowest, queued - s.segment), 3)
                    printer.move(z=queued, feedrate=feedrate)
                    self.steps += 1
                    if started is None:
                        started = time.monotonic()
                    continue
                if queued <= lowest + 1e-9 and estimate <= lowest:
                    break  # the last move should be finishing; see below
                if now >= next_report:
                    self._emit("moving", round(estimate, 2))
                    next_report = now + 0.25
                if now >= next_poll:
                    # Backstop for a missed contact line: the state latches,
                    # and the reply is read below like the unsolicited line.
                    hat.request_probe()
                    next_poll = now + 0.5
                line = hat.read_line(0.05)
                reading = parse_probe_line(line) if line else None
                if reading is None or reading.state == "armed":
                    continue
                if reading.state == "contact":
                    contact = reading
                    break
                self._check_stop()  # the cancel's f aborts the probe
                raise ProbeError(f"The probe stopped during the sweep (state={reading.state})")
        except BaseException:
            # Whatever went wrong, the head must not carry on down.
            self._quickstop_quietly()
            raise

        if contact is not None:
            return self._quickstop(), contact

        # Everything is queued and should be done: let the last move finish
        # and poll, since the state latches.
        printer.wait_for_moves()
        self.session.position["z"] = lowest
        reading = hat.probe()
        self._emit("step", (lowest, reading))
        if reading.state == "contact":
            return lowest, reading
        self._expect_armed(reading, lowest)
        hat.probe("probe stop")
        raise ProbeError(f"No contact down to Z {lowest:g}. Is the cell connected?")

    def _quickstop(self) -> float:
        """M410, then read where the head stopped and make sure it stays there.
        The check uses M114's stepper counts: the reported position is the
        planned one, which would not change if the stop had failed."""
        printer = self.session.rig.printer
        printer.quickstop()
        position, first = printer.report()
        time.sleep(0.2)
        _, second = printer.report()
        if position is None or first is None or second is None:
            printer.wait_for_moves()
            self.session.sync_position()
            raise ProbeError("The printer did not report where it stopped")
        if first != second:
            printer.wait_for_moves()
            self.session.sync_position()
            raise ProbeError(f"M410 did not stop the head (stepper counts {first} then {second})")
        self.session.position["z"] = position[2]
        log.info("Stopped at Z %g", position[2])
        return position[2]

    def _quickstop_quietly(self) -> None:
        try:
            self.session.rig.printer.quickstop()
            self.session.sync_position()
        except Exception as e:
            log.warning("Quickstop after an error failed: %s", e)

    def _restore_feedrate(self) -> None:
        try:
            self.session.rig.printer.set_feedrate(self.settings.feedrate)
        except Exception as e:
            log.warning("Could not restore the feedrate: %s", e)

    # ------------------------------------------------------------ fine / stepped

    def _fine_pass(self, coarse_z: float) -> Tuple[float, ProbeReading]:
        s = self.settings
        if s.speed:
            self._restore_feedrate()  # backoff and steps at normal speed
        # The surface is above where the coarse pass stopped (the sweep
        # overshoots a little) or at most one step above (stepping), so the
        # fine pass never needs to go much below it.
        lowest = max(0.0, coarse_z - s.step)
        for attempt in range(3):
            above = round(coarse_z + s.backoff * (attempt + 1), 3)
            self._state(f"Backing off to Z {above:g}, then {s.fine_step:g} mm steps")
            self._move(above)
            z, reading = self._descend(s.fine_step, lowest)
            if z < above:
                return z, reading
            # Contact at the backed-off height: still touching (the electrode
            # flexed, or a burr). Back off further and try again.
            log.info("Still in contact at Z %g; backing off further", above)
        raise ProbeError(f"Still in contact {3 * s.backoff:g} mm above where the coarse pass stopped. "
                         "Check the electrodes.")

    def _descend(self, step: float, lowest: float) -> Tuple[float, ProbeReading]:
        """Arm the probe and step down until contact. Returns (z, reading)."""
        hat = self.session.rig.hat
        self._arm()
        z = self.session.position["z"]
        while True:
            self._check_stop()
            time.sleep(self.settings.settle)
            reading = hat.probe()
            self._emit("step", (z, reading))
            self._check_stop()  # a cancel aborts the probe, so check before reading the state
            if reading.state == "contact":
                return z, reading
            self._expect_armed(reading, z)
            next_z = round(z - step, 3)
            if next_z < lowest - 1e-9:
                hat.probe("probe stop")
                raise ProbeError(f"No contact down to Z {lowest:g}. Is the cell connected?")
            self._move(next_z)
            z = next_z

    # ------------------------------------------------------------ helpers

    def _arm(self) -> ProbeReading:
        reading = self.session.rig.hat.probe("probe start")
        if reading.state != "armed":
            raise ProbeError(f"The probe did not arm (state={reading.state})")
        return reading

    def _expect_armed(self, reading: ProbeReading, z: float) -> None:
        # A cancel sends f, which aborts the probe: report that as the cancel.
        self._check_stop()
        if reading.state != "armed":
            raise ProbeError(f"The probe stopped at Z {z:g} without contact (state={reading.state})")

    def _move(self, z: float) -> None:
        self._check_stop()
        self.session.move_to(z=z)
        self.session.rig.printer.wait_for_moves()
        self.steps += 1

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise ProbeError("cancelled")

    def _state(self, text: str) -> None:
        log.info("%s", text)
        self._emit("state", text)

    def _emit(self, kind: str, payload: object) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, payload)
            except Exception:
                log.exception("Probe event handler failed")
