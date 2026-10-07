"""The two boards: the ECRIT-HAT console on the R4, and the Marlin printer.

Hat speaks the firmware's console protocol (ECRIT_HAT/ECRIT_HAT.ino):
  r      -> "Reset"         (also how the board is identified)
  c <mA> -> "Hold Current target = ..." or a one-line refusal
  v <V>  -> "Hold Voltage target = ..." or a one-line refusal
  f      -> "Turn off"      (also printed after an interlock trip)
and, while the output is on, telemetry rows "current_mA,target_V,readback_V".
The older sketches answer the same commands.

Printer is plain Marlin ping-pong: every command is answered by a line
starting with "ok", and long commands send "echo:busy" keepalives first.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

from .link import Link, PortInfo, SerialLink, list_ports
from .settings import Options

log = logging.getLogger(__name__)

HAT_BAUD = 9600
PRINTER_BAUDS = (115200, 250000)
# Arduino SA and Arduino.org. Only used to probe likely ports first.
ARDUINO_VIDS = {0x2341, 0x2A03}


class DeviceError(RuntimeError):
    pass


def parse_telemetry(line: str) -> Optional[Tuple[float, float, float]]:
    """(current_mA, target_V, readback_V) from a telemetry row, else None.

    The firmware keeps informational lines free of commas, so anything that
    splits into three numbers is telemetry. Extra columns (format 1) are
    ignored.
    """
    parts = line.split(",")
    if len(parts) < 3:
        return None
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None


@dataclass
class ProbeReading:
    """One `PROBE state=...` line from the HAT's contact probe."""
    state: str                   # idle, armed, contact, timeout, aborted
    current_mA: Optional[float]
    elapsed_ms: Optional[int]
    line: str


_PROBE_FIELD = re.compile(r"(\w+)=(\S+)")


def parse_probe_line(line: str) -> Optional[ProbeReading]:
    if not line.startswith("PROBE "):
        return None
    fields = dict(_PROBE_FIELD.findall(line))
    if "state" not in fields:
        return None

    def number(key, kind):
        try:
            return kind(fields[key])
        except (KeyError, ValueError):
            return None

    return ProbeReading(fields["state"], number("current_mA", float), number("elapsed_ms", int), line)


def format_number(value: float) -> str:
    """Up to three decimals, no trailing zeros: 12.5 -> "12.5", 3.0 -> "3"."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class Hat:
    def __init__(self, link: Link):
        self.link = link

    @property
    def port(self) -> str:
        return self.link.port

    def console(self, line: str, quiet: float = 0.3, timeout: float = 3.0) -> List[str]:
        """Send a console line and collect the reply.

        The reply has no terminator, so it ends after `quiet` seconds without
        a new line (or `timeout` overall, which matters while telemetry is
        streaming).
        """
        self.link.discard_input()
        self.link.write_line(line)
        lines: List[str] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            got = self.link.read_line(min(quiet, remaining) if lines else remaining)
            if got is None:
                break
            lines.append(got)
        return lines

    def _expect(self, command: str, match: Callable[[str], bool], timeout: float, discard: bool = True) -> str:
        if discard:
            self.link.discard_input()
        self.link.write_line(command)
        seen: List[str] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                detail = f" (got: {' | '.join(seen[-3:])})" if seen else ""
                raise DeviceError(f"No reply to {command!r} from the HAT{detail}")
            line = self.link.read_line(remaining)
            if line is None:
                continue
            if match(line):
                return line
            if parse_telemetry(line) is None:
                seen.append(line)

    def reset(self, timeout: float = 2.0) -> None:
        """Send r and wait for "Reset". This is also the identity check."""
        self._expect("r", lambda line: line == "Reset", timeout)

    def use_host_telemetry(self) -> None:
        """Select the 3-column telemetry the run parses (t 0). Best effort:
        the older sketches ignore it."""
        self.console("t 0", quiet=0.2, timeout=0.5)

    def start_output(self, current_mode: bool, target: float, timeout: float = 2.0) -> str:
        """Start constant current (mA) or constant voltage (V) and return the
        board's confirmation. Raises DeviceError if the board refuses."""
        command = ("c " if current_mode else "v ") + format_number(target)
        self.link.discard_input()
        self.link.write_line(command)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeviceError(f"No reply to {command!r} from the HAT")
            line = self.link.read_line(remaining)
            if line is None or parse_telemetry(line) is not None:
                continue
            if line.startswith("Hold"):
                return line
            # "PSU not Connected", "Latched trip. ...", "INA228 not available. ..."
            raise DeviceError(f"HAT refused {command!r}: {line}")

    def zero_current(self, timeout: float = 5.0) -> None:
        """Capture the live current zero (z). The output has to be off."""
        line = self._expect("z", lambda l: l == "Zero calibrated" or l.startswith("Cannot"), timeout)
        if line != "Zero calibrated":
            raise DeviceError(f"HAT refused 'z': {line}")

    def probe(self, command: str = "probe", timeout: float = 2.0) -> ProbeReading:
        """Send a probe command (`probe`, `probe start`, `probe stop`) and
        return the PROBE line it answers with. A refusal raises DeviceError."""
        self.link.discard_input()
        self.link.write_line(command)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeviceError(f"No reply to {command!r} from the HAT")
            line = self.link.read_line(remaining)
            if line is None or parse_telemetry(line) is not None:
                continue
            reading = parse_probe_line(line)
            if reading is not None:
                return reading
            # "PSU not Connected", "Cannot probe while ...", "Latched trip ..."
            raise DeviceError(f"HAT refused {command!r}: {line}")

    def request_probe(self) -> None:
        """Write `probe` without waiting; the PROBE reply arrives like any
        other line (see BaselineProbe's sweep)."""
        self.link.write_line("probe")

    def send_off(self) -> None:
        """Write f and return at once. Safe to call from any thread."""
        self.link.write_line("f")

    def output_off(self, timeout: float = 1.5) -> bool:
        """Write f and wait for "Turn off". False if it never came."""
        self.send_off()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.link.read_line(deadline - time.monotonic()) == "Turn off":
                return True
        return False

    def read_line(self, timeout: float) -> Optional[str]:
        return self.link.read_line(timeout)

    def close(self) -> None:
        self.link.close()


_M114 = re.compile(r"X:\s*(-?[\d.]+)\s+Y:\s*(-?[\d.]+)\s+Z:\s*(-?[\d.]+)")
_M114_COUNT = re.compile(r"Count X:\s*(-?\d+)\s+Y:\s*(-?\d+)\s+Z:\s*(-?\d+)")


class Printer:
    def __init__(self, link: Link):
        self.link = link
        self._lock = threading.RLock()

    @property
    def port(self) -> str:
        return self.link.port

    def send(self, gcode: str, timeout: float = 10.0) -> List[str]:
        """Send one command and wait for its "ok". Returns the lines before it.

        `timeout` is an inactivity timeout: Marlin's busy keepalives restart it.
        """
        with self._lock:
            self.link.discard_input()
            self.link.write_line(gcode)
            lines: List[str] = []
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DeviceError(f"Printer did not answer {gcode!r} within {timeout:g} s")
                line = self.link.read_line(remaining)
                if line is None:
                    continue
                if line.startswith("ok"):
                    return lines
                if line.startswith("echo:busy"):
                    deadline = time.monotonic() + timeout
                    continue
                if line == "start":
                    raise DeviceError("Printer restarted; its position is no longer known")
                if line.startswith("Error:"):
                    log.warning("Printer: %s", line)
                lines.append(line)

    def identify(self, timeout: float = 3.0) -> str:
        """Marlin's M115 firmware line, or "" if it answered without one."""
        for line in self.send("M115", timeout):
            if line.startswith("FIRMWARE_NAME"):
                return line
        return ""

    def position(self) -> Optional[Tuple[float, float, float]]:
        """Position from M114. Marlin reports where the planned moves end,
        not where the head is while it moves."""
        return self.report()[0]

    def report(self) -> Tuple[Optional[Tuple[float, float, float]], Optional[Tuple[int, int, int]]]:
        """M114: (position, stepper counts). The counts are the live stepper
        positions, so two reads that differ mean the head is moving."""
        position = counts = None
        for line in self.send("M114"):
            m = _M114.search(line)
            if m and position is None:
                position = float(m.group(1)), float(m.group(2)), float(m.group(3))
            c = _M114_COUNT.search(line)
            if c:
                counts = int(c.group(1)), int(c.group(2)), int(c.group(3))
        return position, counts

    def move(self, x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None,
             feedrate: Optional[float] = None) -> None:
        """Queue an absolute G1 move. Returns once Marlin accepted it, not when
        the head arrives; see wait_for_moves. `feedrate` is in mm/min and, as
        always in Marlin, stays in effect for later moves."""
        command = "G1"
        for axis, value in (("X", x), ("Y", y), ("Z", z)):
            if value is not None:
                command += f" {axis}{format_number(value)}"
        if command != "G1":
            if feedrate is not None:
                command += f" F{format_number(feedrate)}"
            self.send(command)

    def set_feedrate(self, feedrate: float) -> None:
        """Set the feedrate (mm/min) later moves without F use."""
        self.send(f"G1 F{format_number(feedrate)}")

    def quickstop(self) -> None:
        """M410: stop the planned moves where the head is. Works mid-move
        because G1 does not block Marlin's command queue (M400 and G28 do).
        The ok takes about 2 s on this printer."""
        self.send("M410", timeout=10.0)

    def wait_for_moves(self, timeout: float = 300.0) -> None:
        self.send("M400", timeout)

    def home(self, timeout: float = 300.0) -> None:
        self.send("G28", timeout)

    def absolute_mode(self) -> None:
        self.send("G90")

    def message(self, text: str) -> None:
        """Show text on the printer's LCD (M117)."""
        self.send("M117 " + text)

    def close(self) -> None:
        self.link.close()


@dataclass
class Rig:
    hat: Hat
    printer: Printer

    def close(self) -> None:
        for device in (self.hat, self.printer):
            try:
                device.close()
            except Exception as e:  # closing is best effort
                log.debug("close %s: %s", device.port, e)


# ---------------------------------------------------------------- detection

def _open_link(port: str, baud: int, label: str) -> SerialLink:
    # On POSIX, refuse a port another ECRIT instance already holds.
    return SerialLink(port, baud, label, exclusive=os.name == "posix")


def open_hat(port: str, timeout: float = 1.5) -> Hat:
    """Open the HAT on `port` and confirm it answers. Raises DeviceError."""
    try:
        link = _open_link(port, HAT_BAUD, "hat")
    except Exception as e:
        raise DeviceError(f"Could not open {port}: {e}") from e
    hat = Hat(link)
    try:
        hat.reset(timeout)
    except DeviceError:
        # The first line can be lost to a board that is still booting.
        try:
            hat.reset(timeout)
        except DeviceError as e:
            link.close()
            raise DeviceError(f"No ECRIT-HAT answering on {port}") from e
    return hat


def open_printer(port: str, bauds: Iterable[int] = PRINTER_BAUDS, timeout: float = 1.5) -> Printer:
    """Open the printer on `port`, trying each baud rate. Raises DeviceError."""
    last_error: Optional[Exception] = None
    for baud in bauds:
        try:
            link = _open_link(port, baud, "printer")
        except Exception as e:
            raise DeviceError(f"Could not open {port}: {e}") from e
        printer = Printer(link)
        try:
            firmware = printer.identify(timeout)
            log.info("Printer on %s at %d baud: %s", port, baud, firmware or "(no M115 reply)")
            return printer
        except DeviceError as e:
            last_error = e
            link.close()
    raise DeviceError(f"No printer answering on {port}") from last_error


@dataclass
class Detected:
    hat: Optional[str] = None
    printer: Optional[str] = None


def detect(ports: Optional[List[PortInfo]] = None, want_hat: bool = True, want_printer: bool = True,
           skip: Iterable[str] = ()) -> Detected:
    """Probe USB serial ports for the HAT and the printer.

    Writes "r" (harmless: it only resets the setpoint) and "M115" to each
    candidate. Never opens a port at 1200 baud, which would drop an Arduino
    into its bootloader.
    """
    if ports is None:
        ports = list_ports()
    skip = set(skip)
    candidates = [p for p in ports if p.is_usb and p.device not in skip]
    found = Detected()

    if want_hat:
        for p in sorted(candidates, key=lambda p: p.vid not in ARDUINO_VIDS):
            try:
                open_hat(p.device).close()
            except DeviceError as e:
                log.debug("%s", e)
                continue
            found.hat = p.device
            log.info("Found the ECRIT-HAT on %s", p.device)
            break

    if want_printer:
        for p in sorted(candidates, key=lambda p: p.vid in ARDUINO_VIDS):
            if p.device == found.hat:
                continue
            try:
                open_printer(p.device).close()
            except DeviceError as e:
                log.debug("%s", e)
                continue
            found.printer = p.device
            log.info("Found the printer on %s", p.device)
            break

    return found


@dataclass
class PortCheck:
    """What check_ports found on one port."""
    ok: bool
    detail: str


_FIRMWARE_NAME = re.compile(r"FIRMWARE_NAME:(\S+(?: [\d.]+)?)")
_MACHINE_TYPE = re.compile(r"MACHINE_TYPE:(.+?)(?= [A-Z_]+:|$)")


def describe_hat(hat: Hat) -> str:
    """One line about an open HAT: the PSU line from `s`. The older sketches
    have no `s`, so they only get "answered"."""
    for line in hat.console("s", timeout=2.0):
        if line.startswith("psu: "):
            psu = line[len("psu: "):]
            return "ECRIT-HAT answered, " + ("no PSU connected" if psu == "PSU not Connected" else "PSU: " + psu)
    return "ECRIT-HAT answered"


def describe_printer(printer: Printer) -> str:
    """One line about an open printer, from M115."""
    firmware = printer.identify()
    parts = [m.group(1) for m in (_FIRMWARE_NAME.search(firmware), _MACHINE_TYPE.search(firmware)) if m]
    return "Printer answered" + (": " + ", ".join(parts) if parts else "")


def check_ports(hat_port: str, printer_port: str) -> Tuple[PortCheck, PortCheck]:
    """Open each port as the board it is meant to be and report what answered.

    Sends the same harmless lines as detect ("r", "M115") plus the read-only
    `s`. Both ports are closed again before this returns.
    """
    if hat_port and hat_port == printer_port:
        same = PortCheck(False, "Both devices are set to the same port")
        return same, same

    def check(port: str, opener: Callable, describe: Callable) -> PortCheck:
        if not port:
            return PortCheck(False, "No port selected")
        try:
            device = opener(port)
        except DeviceError as e:
            return PortCheck(False, str(e))
        except Exception as e:  # pyserial missing, permissions
            return PortCheck(False, f"Could not open {port}: {e}")
        try:
            return PortCheck(True, describe(device))
        except DeviceError as e:
            return PortCheck(False, str(e))
        finally:
            device.close()

    return check(hat_port, open_hat, describe_hat), check(printer_port, open_printer, describe_printer)


def connect(options: Options, hat_port: Optional[str] = None, printer_port: Optional[str] = None,
            save: bool = True) -> Rig:
    """Open both boards.

    Ports given here must work. Otherwise the ports saved in options.json are
    tried, and anything that does not answer is found by probing; what was
    found is saved back to options.json.
    """
    hat: Optional[Hat] = None
    printer: Optional[Printer] = None
    try:
        if hat_port:
            hat = open_hat(hat_port)
        elif options.arduino_port:
            try:
                hat = open_hat(options.arduino_port)
            except DeviceError as e:
                log.warning("%s; searching for it", e)

        if printer_port:
            printer = open_printer(printer_port)
        elif options.printer_port:
            try:
                printer = open_printer(options.printer_port)
            except DeviceError as e:
                log.warning("%s; searching for it", e)

        if hat is None or printer is None:
            held = [d.port for d in (hat, printer) if d is not None]
            found = detect(want_hat=hat is None, want_printer=printer is None, skip=held)
            if hat is None and found.hat:
                hat = open_hat(found.hat)
            if printer is None and found.printer:
                printer = open_printer(found.printer)

        missing = [name for name, dev in (("ECRIT-HAT", hat), ("printer", printer)) if dev is None]
        if missing:
            raise DeviceError("Could not find the " + " or the ".join(missing))
    except BaseException:
        for device in (hat, printer):
            if device is not None:
                device.close()
        raise

    if save and (options.arduino_port, options.printer_port) != (hat.port, printer.port):
        options.arduino_port, options.printer_port = hat.port, printer.port
        options.save()

    printer.message("Running ECRIT Application...")
    return Rig(hat, printer)

