"""The list of plating points on the controller page, in run order.

Drag a row to move it in the order (on_move gets first=True for the first
step of each drag). The ✕ at the end of a row, or the Delete
key on the selected row, removes it. The widget only reports these; the
controller changes the session and calls set_points().
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from ..core.pointmap import Point
from . import theme

# (column, heading, width px, anchor)
COLUMNS = (("grip", "", 28, "center"),
           ("n", "#", 36, "center"),
           ("x", "X (mm)", 90, "center"),
           ("y", "Y (mm)", 90, "center"),
           ("delete", "", 36, "center"))
DELETE_COLUMN = f"#{len(COLUMNS)}"


class PointList(tk.Frame):
    def __init__(self, parent: tk.Misc, on_delete: Callable[[int], None], on_move: Callable[[int, int, bool], None],
                 on_select: Callable[[], None], height: int = 6):
        super().__init__(parent, bg=theme.BG)
        self.on_delete, self.on_move = on_delete, on_move
        self.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(self, columns=[c[0] for c in COLUMNS], show="headings", height=height,
                            selectmode="browse", style="Points.Treeview")
        for key, title, width, anchor in COLUMNS:
            tree.heading(key, text=title, anchor=anchor)
            tree.column(key, width=width, minwidth=width, anchor=anchor, stretch=key in ("x", "y"))
        tree.tag_configure("odd", background=theme.CARD_ALT)
        tree.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=tree.yview, style="Points.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        tree.config(yscrollcommand=self._scrolled)
        self.scroll = scroll
        self.tree = tree

        self.shown: List[Point] = []
        self.dragging: Optional[str] = None  # the row being dragged
        self.dragged = False                 # it has moved in this drag
        tree.bind("<ButtonPress-1>", self._press)
        tree.bind("<B1-Motion>", self._drag)
        tree.bind("<ButtonRelease-1>", self._release)
        tree.bind("<Motion>", self._hover)
        tree.bind("<Delete>", self._delete_key)
        tree.bind("<BackSpace>", self._delete_key)
        tree.bind("<<TreeviewSelect>>", lambda _event: on_select())

    def set_points(self, points: List[Point]) -> None:
        """Show `points`. Rebuilds, and clears the selection, only if they
        changed."""
        if points == self.shown:
            return
        grew = len(points) > len(self.shown)
        tree = self.tree
        tree.delete(*tree.get_children())
        for i, (x, y) in enumerate(points):
            tree.insert("", "end", iid=str(i), values=("≡", i + 1, f"{x:.2f}", f"{y:.2f}", "✕"))
        self.shown = list(points)
        self._renumber()
        if grew:
            tree.see(str(len(points) - 1))

    def _scrolled(self, first: str, last: str) -> None:
        """Show the scrollbar only while some rows are out of view."""
        self.scroll.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.scroll.grid_remove()
        else:
            self.scroll.grid()

    def selected(self) -> Optional[int]:
        selection = self.tree.selection()
        return self.tree.index(selection[0]) if selection else None

    def _renumber(self) -> None:
        for i, iid in enumerate(self.tree.get_children()):
            self.tree.set(iid, "n", i + 1)
            self.tree.item(iid, tags=("odd",) if i % 2 else ())

    def _press(self, event: tk.Event):
        tree = self.tree
        self.dragging = None
        if tree.identify_region(event.x, event.y) in ("heading", "separator"):
            return "break"  # no sorting or column resizing
        iid = tree.identify_row(event.y)
        if not iid:
            return None
        if tree.identify_column(event.x) == DELETE_COLUMN:
            self.on_delete(tree.index(iid))
            return "break"
        self.dragging = iid  # the default binding still selects it
        self.dragged = False
        tree.focus_set()
        return None

    def _drag(self, event: tk.Event) -> None:
        tree = self.tree
        if self.dragging is None:
            return
        tree.config(cursor="sb_v_double_arrow")
        target = tree.identify_row(event.y)
        if not target or target == self.dragging:
            return
        src, dst = tree.index(self.dragging), tree.index(target)
        tree.move(self.dragging, "", dst)
        tree.see(self.dragging)
        self.shown.insert(dst, self.shown.pop(src))
        self._renumber()
        self.on_move(src, dst, not self.dragged)
        self.dragged = True

    def _release(self, _event: tk.Event) -> None:
        self.dragging = None
        self.tree.config(cursor="")

    def _hover(self, event: tk.Event) -> None:
        if self.dragging is not None:
            return
        tree = self.tree
        on_row = bool(tree.identify_row(event.y))
        column = tree.identify_column(event.x)
        if on_row and column == DELETE_COLUMN:
            cursor = "hand2"
        elif on_row:
            cursor = "fleur" if column == "#1" else ""
        else:
            cursor = ""
        tree.config(cursor=cursor)

    def _delete_key(self, _event: tk.Event) -> str:
        index = self.selected()
        if index is not None:
            self.on_delete(index)
        return "break"
