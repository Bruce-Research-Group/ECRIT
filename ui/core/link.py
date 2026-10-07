"""Line-oriented serial I/O.

Both boards talk in newline-terminated text lines. A Link hides the port:
SerialLink wraps pyserial, and ui.core.sim provides fake ones with the same
methods. pyserial is imported lazily so the simulator works without it.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

log = logging.getLogger(__name__)


class Link:
    """Interface shared by SerialLink and the simulated links."""

    port: str = ""

    def write_line(self, text: str) -> None:
        raise NotImplementedError

    def read_line(self, timeout: float) -> Optional[str]:
        """Next line without its line ending, or None after `timeout` seconds."""
        raise NotImplementedError

    def discard_input(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class SerialLink(Link):
    # Reads poll in short slices so read_line can honour its own timeout.
    POLL_S = 0.05

    def __init__(self, port: str, baudrate: int, label: str = "", exclusive: bool = False):
        import serial

        self.port = port
        self.baudrate = baudrate
        self.label = label or port
        kwargs = {"exclusive": True} if exclusive else {}
        self._serial = serial.Serial(port, baudrate, timeout=self.POLL_S, write_timeout=1, **kwargs)
        self._buffer = bytearray()
        # Writes can come from two threads: a run reading telemetry and the
        # cancel button sending "f".
        self._write_lock = threading.Lock()

    def write_line(self, text: str) -> None:
        log.debug("%s > %s", self.label, text)
        with self._write_lock:
            self._serial.write((text + "\n").encode())

    def read_line(self, timeout: float) -> Optional[str]:
        deadline = time.monotonic() + timeout
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                line = raw.decode(errors="replace").strip()
                log.debug("%s < %s", self.label, line)
                return line
            if time.monotonic() >= deadline:
                return None
            chunk = self._serial.read(max(1, self._serial.in_waiting))
            if chunk:
                self._buffer.extend(chunk)

    def discard_input(self) -> None:
        self._serial.reset_input_buffer()
        self._buffer.clear()

    def close(self) -> None:
        self._serial.close()


@dataclass
class PortInfo:
    device: str
    description: str = ""
    vid: Optional[int] = None
    pid: Optional[int] = None

    @property
    def is_usb(self) -> bool:
        return self.vid is not None

    def __str__(self) -> str:
        ids = f" [{self.vid:04x}:{self.pid:04x}]" if self.vid is not None and self.pid is not None else ""
        return f"{self.device} ({self.description}){ids}" if self.description else self.device + ids


def list_ports() -> List[PortInfo]:
    from serial.tools import list_ports as lp

    ports = [PortInfo(p.device, p.description or "", p.vid, p.pid) for p in lp.comports()]
    return sorted(ports, key=lambda p: p.device)
