"""Colours and ttk styles shared by the windows."""

import tkinter as tk
from tkinter import ttk

BG = "#2E3440"          # window background
ACCENT = "#3E9B8B"      # Start / Next / Start Electroplating, the selected mode and step
BACK = "#7A3A30"        # Go Back
CANCEL = "#bc5c5c"      # Cancel Experiment
CANCELLED = "#8E5454"   # Cancel Experiment, after it was pressed
CARD = "#3B4252"        # buttons, mode cards, the point map and list
CARD_LINE = "#5A6578"   # borders of those; separators
CARD_ALT = "#353C4A"    # every other row of the point list
CARD_ON = "#9FE0D2"     # border of the selected mode card (filled with ACCENT)
WARN = "#EBCB8B"        # a parameter that is not a number; baseline not set
HEAD = "#D08770"        # the head on the point map
MUTED = "#959393"       # Add Point Here before a baseline is set
SUBTLE = "#AEB6C4"      # secondary text on BG
GOOD = "#8FD694"        # a port test that passed
BAD = "#F29B9B"         # a port test that failed
FONT = ("Helvetica", 12)


def button(parent: tk.Misc, text: str, command, **kw) -> tk.Button:
    """The dark button used on every page."""
    options = dict(bg=CARD, fg="white", activebackground=CARD_LINE, activeforeground="white",
                   disabledforeground=CARD_LINE, highlightthickness=0)
    options.update(kw)
    return tk.Button(parent, text=text, command=command, **options)


def accent_button(parent: tk.Misc, text: str, command, **kw) -> tk.Button:
    """The button that moves on to the next step (Start, Next, Confirm)."""
    options = dict(bg=ACCENT, fg="white", activebackground="#4DB3A1", activeforeground="white",
                   font="Helvetica 11 bold")
    options.update(kw)
    return button(parent, text, command, **options)


def apply(root: tk.Tk) -> None:
    root.configure(background=BG)
    style = ttk.Style(root)
    style.configure("TButton", font=FONT, padding=6, foreground="#FFFFFF", background="#4CAF50", borderwidth=0)
    style.map("TButton",
              foreground=[("pressed", "#FFFFFF"), ("active", "#FFFFFF"), ("!disabled", "#FFFFFF")],
              background=[("pressed", "#388E3C"), ("active", "#45A049"), ("!disabled", "#4CAF50")])
    style.configure("TLabel", font=FONT, foreground="#FFFFFF", background=BG)
    style.configure("TRadiobutton", font=FONT, foreground="#FFFFFF", background=BG)
    style.configure("TFrame", background=BG)
    # The point list on the controller page.
    style.configure("Points.Treeview", background=CARD, fieldbackground=CARD, foreground="white",
                    font=("Helvetica", 11), rowheight=26, borderwidth=0)
    style.map("Points.Treeview", background=[("selected", WARN)], foreground=[("selected", BG)])
    style.layout("Points.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no border
    style.configure("Points.Treeview.Heading", background=CARD_LINE, foreground="white",
                    font=("Helvetica", 10, "bold"), relief="flat", borderwidth=0, padding=(6, 4))
    style.map("Points.Treeview.Heading", background=[("active", CARD_LINE)], relief=[("pressed", "flat")])
    style.configure("Run.Horizontal.TProgressbar", background=ACCENT, troughcolor=CARD, borderwidth=0,
                    thickness=10)
    style.configure("Points.Vertical.TScrollbar", background=CARD_LINE, troughcolor=CARD, borderwidth=0,
                    arrowcolor="white")
