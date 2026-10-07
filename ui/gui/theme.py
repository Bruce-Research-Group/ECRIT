"""Colours and ttk styles shared by the windows."""

import tkinter as tk
from tkinter import ttk

BG = "#2E3440"          # window background
PANEL = "#646f7a"       # lower button panel
PAD = "#4C5E85"         # jog pad frames
ACCENT = "#3E9B8B"      # Start / Next / START ELECTROPLATING
BACK = "#7A3A30"        # Go Back
CANCEL = "#bc5c5c"      # Cancel Experiment
CANCELLED = "#8E5454"   # Cancel Experiment, after it was pressed
SELECTED = "#b1c6eb"    # the active mode button
MUTED = "#959393"       # Set Geometric Area before a baseline is set
FONT = ("Helvetica", 12)


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
