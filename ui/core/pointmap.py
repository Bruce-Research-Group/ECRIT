"""Geometry for the map of plating points on the controller page, without Tk:
the view that fits the points, and the grid and scale bar length.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

Point = Tuple[float, float]


@dataclass
class View:
    """Bed coordinates (mm) to canvas pixels. +X is right and +Y is up,
    unless inverted."""
    cx: float       # bed coordinate at the centre of the canvas
    cy: float
    scale: float    # px per mm
    width: int      # canvas size, px
    height: int
    invert_x: bool = False
    invert_y: bool = False

    def to_px(self, x: float, y: float) -> Tuple[float, float]:
        dx = (x - self.cx) * self.scale
        dy = (y - self.cy) * self.scale
        return (self.width / 2 + (-dx if self.invert_x else dx),
                self.height / 2 + (dy if self.invert_y else -dy))

    @property
    def span(self) -> Tuple[float, float]:
        """Width and height of the area shown, mm."""
        return self.width / self.scale, self.height / self.scale

    def contains(self, x: float, y: float) -> bool:
        px, py = self.to_px(x, y)
        return 0 <= px <= self.width and 0 <= py <= self.height


def fit_view(points: Sequence[Point], width: int, height: int, bed: Point,
             margin: float = 0.15, min_span: float = 10.0,
             invert_x: bool = False, invert_y: bool = False) -> View:
    """The view that shows every point with a margin around them: `margin`
    times the points' extent (or `min_span`, whichever is larger), and at
    least 2 mm. With no points, the whole bed."""
    width, height = max(1, width), max(1, height)
    if points:
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = max(margin * max(x1 - x0, y1 - y0, min_span), 2.0)
        span_x = max(x1 - x0, min_span) + 2 * pad
        span_y = max(y1 - y0, min_span) + 2 * pad
    else:
        x0, x1, y0, y1 = 0.0, bed[0], 0.0, bed[1]
        pad = 0.04 * max(bed)
        span_x, span_y = bed[0] + 2 * pad, bed[1] + 2 * pad
    scale = min(width / span_x, height / span_y)
    return View((x0 + x1) / 2, (y0 + y1) / 2, scale, width, height, invert_x, invert_y)


def nice_length(limit: float) -> float:
    """The largest 1, 2 or 5 times a power of ten that is at most `limit`:
    the grid spacing and scale bar length for the map."""
    if not limit > 0 or not math.isfinite(limit):
        return 0.0
    power = 10.0 ** math.floor(math.log10(limit))
    for factor in (5, 2, 1):
        if factor * power <= limit * (1 + 1e-9):
            return round(factor * power, 12)
    return power
