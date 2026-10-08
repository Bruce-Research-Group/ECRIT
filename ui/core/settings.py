"""Settings files.

config.json holds the rig defaults and is only read. options.json holds this
machine's port choice and the last save folder; it is gitignored and written
whenever those change. Both live in the repository root, wherever the program
is started from.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Dict

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.json"
OPTIONS_PATH = REPO_ROOT / "options.json"


@dataclass
class Config:
    # mode: True for constant current, False for constant voltage
    current_mode: bool = True
    # target current in mA
    target_current: float = 63.0
    # target voltage in V
    target_voltage: float = 5.0
    # plating time at each point, in seconds
    duration: float = 10.0
    # distance between the electrode and the baseline height while plating, mm
    diff_z: float = 1.0
    # height the head travels at between runs, mm
    travel_z: float = 110.0
    # record the reference electrode (CN4) during runs; off for a two-electrode cell
    reference_electrode: bool = False

    # machine limits, mm
    x_limit: float = 235.0
    y_limit: float = 235.0
    z_limit: float = 200.0

    # assumed position when the printer cannot report one
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0

    # baseline (surface) height until the user sets one
    tar_z: float = 90.0

    # "Go To Start Point": rise to start_clear_z, move over, drop to start_z
    start_x: float = 130.0
    start_y: float = 140.0
    start_z: float = 60.0
    start_clear_z: float = 120.0

    # Feedrate (mm/min) the printer is left at after a slow probe sweep.
    # 1500 is Marlin's own power-on default.
    travel_feedrate: float = 1500.0

    # The point map on the controller page shows +X to the right and +Y up.
    # Set these to flip an axis to match how the bed looks from the operator.
    map_invert_x: bool = False
    map_invert_y: bool = False

    # "Probe Baseline Height": the "probe" object in config.json. Its keys are
    # ProbeSettings fields (ui.core.probe), which also hold the defaults and
    # what each one means; missing keys keep their default.
    probe: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        with open(path, "r") as f:
            data = json.load(f)
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            log.debug("config.json: ignoring %s", ", ".join(unknown))
        return cls(**{k: v for k, v in data.items() if k in known})

    def limit(self, axis: str) -> float:
        return {"x": self.x_limit, "y": self.y_limit, "z": self.z_limit}[axis]


@dataclass
class Options:
    # Key names match the options.json files already out there.
    arduino_port: str = ""
    printer_port: str = ""
    csv_filepath: str = ""
    path: Path = field(default=OPTIONS_PATH, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path = OPTIONS_PATH) -> "Options":
        options = cls(path=path)
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            return options
        except (OSError, ValueError) as e:
            log.warning("Could not read %s (%s); using defaults", path, e)
            return options
        for key in ("arduino_port", "printer_port", "csv_filepath"):
            value = data.get(key)
            if isinstance(value, str):
                setattr(options, key, value)
        return options

    def save(self) -> None:
        data = asdict(self)
        del data["path"]
        with open(self.path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
