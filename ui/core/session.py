"""What the controller window keeps track of, without the window.

The GUI and the CLI shell both drive a Session: jog the head, mark the
baseline height and the geometric areas, set the plating parameters, and build
the RunParams for a run.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .devices import Rig
from .plating import RunParams
from .settings import Config

log = logging.getLogger(__name__)

AXES = ("x", "y", "z")


class Session:
    def __init__(self, rig: Rig, config: Config):
        self.rig = rig
        self.config = config

        # Last commanded position. Replaced by what the printer reports in
        # start(), so the first jog is relative to where the head really is.
        self.position: Dict[str, float] = {"x": config.pos_x, "y": config.pos_y, "z": config.pos_z}

        # Surface height and the points to plate at.
        self.baseline_z = config.tar_z
        self.baseline_set = False
        self.points: List[Tuple[float, float]] = []

        # Plating parameters, starting from config.json.
        self.current_mode = config.current_mode
        self.target_current = config.target_current
        self.target_voltage = config.target_voltage
        self.distance = config.diff_z
        self.duration = config.duration
        self.reference = config.reference_electrode

    # ------------------------------------------------------------ motion

    def start(self) -> None:
        """Put the printer in absolute mode and read where the head is."""
        self.rig.printer.absolute_mode()
        self.sync_position()

    def sync_position(self) -> bool:
        reported = self.rig.printer.position()
        if reported is None:
            log.warning("The printer did not report a position; assuming %s", self.position)
            return False
        self.position = dict(zip(AXES, reported))
        return True

    def home(self) -> None:
        self.rig.printer.home()
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}

    def move_to(self, x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None) -> None:
        """Absolute move. Refuses targets outside the machine limits."""
        targets = {"x": x, "y": y, "z": z}
        for axis, value in targets.items():
            if value is not None and not 0 <= value <= self.config.limit(axis):
                raise ValueError(f"{axis.upper()} {value:g} is outside 0..{self.config.limit(axis):g} mm")
        self.rig.printer.move(x=x, y=y, z=z)
        for axis, value in targets.items():
            if value is not None:
                self.position[axis] = value

    def jog(self, axis: str, amount: float) -> float:
        """Move one axis by `amount` mm, clamped to the machine limits.
        Returns the new coordinate."""
        target = self.position[axis] + amount
        target = round(min(self.config.limit(axis), max(0.0, target)), 3)
        self.move_to(**{axis: target})
        return target

    def go_to_start_point(self) -> None:
        """Rise to the clearance height, move over the start point, drop."""
        c = self.config
        self.move_to(z=c.start_clear_z)
        self.move_to(x=c.start_x, y=c.start_y)
        self.move_to(z=c.start_z)

    # ------------------------------------------------------------ marking

    def set_baseline(self, z: Optional[float] = None) -> float:
        """Record the surface height: `z`, or the head's Z if not given.
        BaselineProbe (ui.core.probe) finds it by touching the cathode."""
        self.baseline_z = self.position["z"] if z is None else z
        self.baseline_set = True
        return self.baseline_z

    def add_point(self) -> bool:
        """Add the head's x,y as a geometric area. False if already added."""
        point = (self.position["x"], self.position["y"])
        if point in self.points:
            return False
        self.points.append(point)
        return True

    def undo_point(self) -> Optional[Tuple[float, float]]:
        return self.points.pop() if self.points else None

    # ------------------------------------------------------------ run

    def run_params(self) -> RunParams:
        """Parameters for a run from the current state. Raises ValueError,
        with one problem per line, if they would not make a sane run."""
        params = RunParams(
            points=list(self.points),
            baseline_z=self.baseline_z,
            distance=self.distance,
            duration=self.duration,
            current_mode=self.current_mode,
            target_current=self.target_current,
            target_voltage=self.target_voltage,
            travel_z=self.config.travel_z,
            reference=self.reference,
        )
        params.check(self.config)
        return params
