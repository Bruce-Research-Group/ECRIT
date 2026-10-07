#!/usr/bin/env python3
# Launcher for the electroplating UI. The code itself lives in ui/.

import os
import runpy
import sys

root = os.path.dirname(os.path.abspath(__file__))
ui_dir = os.path.join(root, "ui")

# The UI modules import each other by bare name, and they open config.json
# and options.json relative to the working directory, which stay at the root.
os.chdir(root)
sys.path.insert(0, ui_dir)

# Run it as __main__ like before. ElectroplatingUI's "from SendCommandSerial
# import *" relies on that to load a second, complete copy of the module
# rather than the half-imported one that is mid-way through importing it.
runpy.run_path(os.path.join(ui_dir, "SendCommandSerial.py"), run_name="__main__")
