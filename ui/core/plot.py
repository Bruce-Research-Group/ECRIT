"""The voltage and current vs. time plot shown after a run.

Runs with the reference electrode get a second panel underneath, on the same
time axis: the working electrode's potential against the reference.

Builds a bare matplotlib Figure (no pyplot), so it works from any thread and
without a display. The GUI embeds it; the CLI saves it to a file.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .plating import REFERENCE_COLUMN, Sample

VOLTAGE_COLOR = "red"
CURRENT_COLOR = "blue"
REFERENCE_COLOR = "green"
SPAN_COLOR = "#7dea827c"
LABEL_COLOR = "#5590b0cd"


def make_figure(samples: List[Sample], points: List[Tuple[float, float]], duration: float):
    from matplotlib.figure import Figure
    from matplotlib.ticker import FormatStrFormatter, MaxNLocator

    reference = any(s.we_vs_re_V is not None for s in samples)
    if reference:
        fig = Figure(figsize=(8, 7.5))
        fig.suptitle("Plot of Voltage (V), Current (mA) and WE vs RE (V) vs. Time (s)")
        ax, axr = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": (3, 2)})
        axes = (ax, axr)
        axr.set_xlabel("Time (Seconds)")
    else:
        fig = Figure(figsize=(8, 5))
        fig.suptitle("Plot of Voltage (V) and Current (mA) vs. Time (s)")
        ax = fig.add_subplot()
        axes = (ax,)
        ax.set_xlabel("Time (Seconds)")

    t = [s.t_total for s in samples]
    ax.plot(t, [s.voltage_V for s in samples], "-o", color=VOLTAGE_COLOR, label="Voltage (V)")
    ax.set_ylabel("Voltage (V)", color=VOLTAGE_COLOR, labelpad=20)
    ax.tick_params(axis="y", colors=VOLTAGE_COLOR)

    axc = ax.twinx()
    axc.plot(t, [s.current_mA for s in samples], "-o", color=CURRENT_COLOR, label="Current (mA)")
    axc.set_ylabel("Current (mA)", color=CURRENT_COLOR, labelpad=20)
    axc.tick_params(axis="y", colors=CURRENT_COLOR)

    if reference:
        # NaN (no reading) leaves a gap in the line.
        axr.plot(t, [math.nan if s.we_vs_re_V is None else s.we_vs_re_V for s in samples], "-o",
                 color=REFERENCE_COLOR, label="WE vs RE (V)")
        axr.set_ylabel("WE vs RE (V)", color=REFERENCE_COLOR, labelpad=20)
        axr.tick_params(axis="y", colors=REFERENCE_COLOR)
        axr.yaxis.set_major_locator(MaxNLocator(nbins=5))

    for axis in (ax.xaxis, ax.yaxis, axc.yaxis):
        axis.set_major_locator(MaxNLocator(nbins=6))
    axes[-1].xaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    # A steady trace (WE vs RE, or the voltage in voltage mode) spans far less
    # than its value, and matplotlib would then label the ticks relative to an
    # offset printed above the axis (-1.034 and -0.00026...). Label them in full.
    for a in (*axes, axc):
        a.ticklabel_format(axis="y", useOffset=False)

    # Each point owns [i * duration, (i + 1) * duration) of the accumulated
    # time axis. Shade every other one and label each with its position.
    font_size = max(6.0, 14.0 / max(1, len(points)) ** 0.5)
    for i, (x, y) in enumerate(points):
        start, end = i * duration, (i + 1) * duration
        if len(points) > 1 and i % 2 == 0:
            for a in axes:
                a.axvspan(start, end, color=SPAN_COLOR)
        ax.text((start + end) / 2, 0.97, f"X: {x:g}\nY: {y:g}", transform=ax.get_xaxis_transform(),
                ha="center", va="top", size=font_size, color=LABEL_COLOR)

    if reference:
        # Three entries stacked in the corner would run into the title.
        fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.955), ncol=3)
        fig.tight_layout(rect=(0, 0, 1, 0.91))
    else:
        fig.legend()
        fig.tight_layout(rect=(0, 0, 1, 0.9))
    return fig


def save_plot(path: Path, samples: List[Sample], points: List[Tuple[float, float]], duration: float) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = make_figure(samples, points, duration)
    FigureCanvasAgg(fig)
    fig.savefig(str(path), dpi=120)


def load_run(csv_path: Path) -> Tuple[List[Sample], List[Tuple[float, float]], Optional[float]]:
    """Read a run back from its CSV, plus the matching log_*.txt if it is
    next to it (for the point positions and the duration)."""
    csv_path = Path(csv_path)
    samples: List[Sample] = []
    point = -1
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        reference = len(header) > 5 and header[5] == REFERENCE_COLUMN
        for row in reader:
            if not any(row):
                point += 1
                continue
            cur, tar, vol, t_point, t_total = (float(v) for v in row[:5])
            sample = Sample(max(point, 0), cur, tar, vol, t_point, t_total)
            if reference:
                sample.we_vs_re_V = float(row[5]) if len(row) > 5 and row[5] else math.nan
            samples.append(sample)

    points: List[Tuple[float, float]] = []
    duration = None
    log_path = csv_path.with_suffix(".txt")
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            m = re.match(r"x: (-?[\d.]+), y: (-?[\d.]+)$", line)
            if m:
                points.append((float(m.group(1)), float(m.group(2))))
            m = re.match(r"duration (-?[\d.]+)s$", line)
            if m:
                duration = float(m.group(1))
    return samples, points, duration
