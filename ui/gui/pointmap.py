"""The map of plating points on the controller page.

Zooms to fit the points with a margin, numbers them in run order with arrows
between them, marks the head, and has a grid and scale bar at the bottom.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import List, Optional, Tuple

from ..core.pointmap import Point, View, fit_view, nice_length
from . import theme

STRIP = 28      # px at the bottom for the scale bar
RADIUS = 10     # point marker, px
GRID = "#434C5E"


def _mm(value: float) -> str:
    return f"{value:.3g}"


class PointMap(tk.Canvas):
    def __init__(self, parent: tk.Misc, bed: Point, invert_x: bool = False, invert_y: bool = False):
        super().__init__(parent, width=400, height=300, bg=theme.CARD, highlightthickness=1,
                         highlightbackground=theme.CARD_LINE)
        self.bed = bed
        self.invert_x, self.invert_y = invert_x, invert_y
        self.points: List[Point] = []
        self.head: Optional[Point] = None
        self.selected: Optional[int] = None
        self.bind("<Configure>", lambda _event: self.redraw())

    def show(self, points: List[Point], head: Optional[Point], selected: Optional[int] = None) -> None:
        self.points, self.head, self.selected = list(points), head, selected
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height() - STRIP
        if width < 40 or height < 40:  # not laid out yet
            return
        view = fit_view(self.points, width, height, self.bed, invert_x=self.invert_x, invert_y=self.invert_y)
        step = nice_length(view.span[0] / 4)
        self._grid(view, step)
        x0, y0 = view.to_px(0, 0)
        x1, y1 = view.to_px(*self.bed)
        self.create_rectangle(x0, y0, x1, y1, outline=theme.CARD_LINE, dash=(4, 3))
        self._path(view)
        self._head(view)
        self._scale_bar(view, step)
        axes = f"+X {'←' if self.invert_x else '→'}   +Y {'↓' if self.invert_y else '↑'}"
        self.create_text(8, 6, text=axes, anchor="nw", fill=theme.SUBTLE, font="Helvetica 9")
        if not self.points:
            self.create_text(width / 2, height / 2, text="No points yet.\nMove the head and press Add Point Here.",
                             fill=theme.SUBTLE, justify="center", font="Helvetica 11")

    def _grid(self, view: View, step: float) -> None:
        if not step:
            return
        span_x, span_y = view.span
        x = math.floor((view.cx - span_x / 2) / step) * step
        while x <= view.cx + span_x / 2:
            px, _ = view.to_px(x, 0)
            self.create_line(px, 0, px, view.height, fill=GRID)
            x += step
        y = math.floor((view.cy - span_y / 2) / step) * step
        while y <= view.cy + span_y / 2:
            _, py = view.to_px(0, y)
            self.create_line(0, py, view.width, py, fill=GRID)
            y += step

    def _path(self, view: View) -> None:
        pxs = [view.to_px(x, y) for x, y in self.points]
        # Arrows between consecutive points, stopping at the marker's edge.
        for (ax, ay), (bx, by) in zip(pxs, pxs[1:]):
            length = math.hypot(bx - ax, by - ay)
            if length <= 2 * RADIUS + 4:
                continue
            ux, uy = (bx - ax) / length, (by - ay) / length
            self.create_line(ax + ux * RADIUS, ay + uy * RADIUS, bx - ux * (RADIUS + 1), by - uy * (RADIUS + 1),
                             fill=theme.ACCENT, width=2, arrow="last", arrowshape=(9, 11, 4))
        for i, (px, py) in enumerate(pxs):
            selected = i == self.selected
            self.create_oval(px - RADIUS, py - RADIUS, px + RADIUS, py + RADIUS,
                             fill=theme.WARN if selected else theme.ACCENT, outline="white", width=1)
            self.create_text(px, py, text=str(i + 1), fill=theme.BG if selected else "white",
                             font="Helvetica 9 bold")

    def _head(self, view: View) -> None:
        if self.head is None:
            return
        if not view.contains(*self.head):
            self.create_text(view.width - 8, 6, text="head is outside this view", anchor="ne",
                             fill=theme.HEAD, font="Helvetica 9")
            return
        px, py = view.to_px(*self.head)
        self.create_line(px - 14, py, px + 14, py, fill=theme.HEAD, width=2)
        self.create_line(px, py - 14, px, py + 14, fill=theme.HEAD, width=2)
        self.create_oval(px - 5, py - 5, px + 5, py + 5, outline=theme.HEAD, width=2)

    def _scale_bar(self, view: View, step: float) -> None:
        top = view.height
        bottom = top + STRIP
        self.create_rectangle(0, top, view.width, bottom, fill=theme.CARD, outline="")
        self.create_line(0, top, view.width, top, fill=theme.CARD_LINE)
        mid = top + STRIP / 2
        if step:
            x0, x1 = 10, 10 + step * view.scale
            self.create_line(x0, mid, x1, mid, fill="white", width=2)
            for x in (x0, x1):
                self.create_line(x, mid - 5, x, mid + 5, fill="white", width=2)
            self.create_text(x1 + 8, mid, text=f"{step:g} mm  (grid)", anchor="w", fill="white",
                             font="Helvetica 10")
        span_x, span_y = view.span
        self.create_text(view.width - 10, mid, text=f"view {_mm(span_x)} × {_mm(span_y)} mm",
                         anchor="e", fill=theme.SUBTLE, font="Helvetica 10")
        self.create_text(view.width / 2 + 40, mid, text="✛ head", anchor="w", fill=theme.HEAD,
                         font="Helvetica 10")
