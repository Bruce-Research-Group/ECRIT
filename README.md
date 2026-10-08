<div align="center">
	<h1>ECRIT Electroplating System</h1>

![Project Logo](/Screenshots/ControllerMenu.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
</div>

## Table of Contents
1. [About the Project](#about-the-project)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Usage](#usage)
5. [License](#license)

# About Ecrit
This is a system for controlling an electroplating experiment using a 3D printer and Arduino Uno.

## Prerequisites
1. Ensure you have Python installed on your system. You can download it from [python.org](https://www.python.org/downloads/).
2. Download and install the arduino IDE from [arduino.cc](https://www.arduino.cc/en/software/)

## Installation
### Set Up UI
1. Clone the repository.
```bash
git clone https://github.com/Bruce-Research-Group/ECRIT
```
2. Install the required Python packages:
```bash
pip install -r requirements.txt
```
3. Make gui file executable:
```bash
chmod +x SendCommandSerial.py
```
4. To run the gui and to view it, run the following command in the terminal or open "SendCommandSerial.py" through the file explorer
```bash
./SendCommandSerial.py
```
`SendCommandSerial.py` in the repository root only launches the UI. Add `--sim` to try it with simulated boards, without any hardware connected. Settings are read from `config.json` in the repository root, and the chosen ports and save folder are kept in `options.json` next to it.

The code lives in `ui/`:

| Path | What |
|---|---|
| `ui/core/` | Everything that talks to the hardware, with no Tk: settings, the HAT and printer protocols, port detection, the plating sequence, the plot, and simulated boards |
| `ui/gui/` | The Tkinter windows |
| `ui/cli.py` | The command-line version (below) |
| `tests/` | Tests against the simulated boards: `python3 -m unittest discover tests` |

### Command line
`ecrit_cli.py` does what the GUI does without a display, which is handy over ssh and for scripted tests. `./ecrit_cli.py -h` lists the commands; a few examples:
```bash
./ecrit_cli.py ports                 # list serial ports
./ecrit_cli.py detect --save         # find the HAT and the printer, remember them
./ecrit_cli.py status                # printer firmware and HAT status
./ecrit_cli.py hat s                 # send any console line to the HAT
./ecrit_cli.py gcode M114            # send any G-code to the printer
./ecrit_cli.py baseline --max-travel 20  # find the baseline height below the head
./ecrit_cli.py run --point 146,124 --point 150,124 --baseline 44.9 \
    --distance 1 --duration 10 --current 63 --plot run.png
./ecrit_cli.py shell                 # the controller window as commands: home, jog, baseline, point, start, ...
./ecrit_cli.py --sim shell           # the same, with simulated boards
```
`run` and the shell's `start` ask before moving the head and turning the output on; pass `-y` to skip the question. Runs are saved to `experiment_logs/` unless `--out` says otherwise. The shell also reads commands from a pipe, for example `printf 'home\npos\n' | ./ecrit_cli.py shell`.

### Set Up Arduino
1. Open the arduino IDE
2. Click File
3. Click Open File and find the cloned repository from the UI setup.
4. Open the Eletroplating_Serial_R4 folder and open the "Electroplating_Serial_R4.ino" file within
5. After the file opens, select the arduino board and upload the code to the board. For further information on how to do so use the guide linked [here](https://support.arduino.cc/hc/en-us/articles/4733418441116-Upload-a-sketch-in-Arduino-IDE)

With the ECRIT-HAT shield on an Uno R4 WiFi, upload `ECRIT_HAT/ECRIT_HAT.ino` instead (it needs the Adafruit ADS1X15 and Adafruit INA228 libraries). "Probe Baseline Height" only works with this firmware. `ECRIT_HAT/CALIBRATION.md` describes its serial console and calibration.

## Usage
- A GUI to conduct electroplating experiments easily
- A analysis-tool for quick access to experiment data / information

1. Upon starting the program you are presented with the following start menu. To begin click "Start" to start the program.

![](/Screenshots/StartMenu.png)

2. If successful, the program will open to the controller menu. Here start by clearing any possible obstructions out of the way of your 3D printer, then click the home button to ensure your printer starts at the right position.

![](Screenshots/ControllerMenu.png)

**Troubleshooting**: If this operation does not result in any change in the 3D printer; you may have to restart the program and click the configure ports button instead. Click the dropdown to select your corresponding arduino and 3D printer ports. Click "Test" to check that the ECRIT-HAT and the printer answer on the selected ports (or "Detect" to search for them), then click the confirm button to complete the port selection. After successfully updating your ports, click the "Start" button on the start menu.

![](Screenshots/PortMenu.png)

Ensure that your experimental apparatus is setup according to the procedure given in the research paper.
The up and down arrows labeled "z-axis" are used to move the printer head up and down. The "y-axis controls forwards and backwards and the "x-axis controls left and right. Under the “Select Printer Step Size” option, whatever number you choose determines the travel distance of the platinum electrode or the cell.

WARNING: If the number you choose from the “Select Printer Step Size” is more than the distance between your electrode and your cell, the electrode will crash into the cell. 

3. Now use the arrow buttons to position the electrode attached to the printer head over the geometric surface area on the substrate, a little above the surface, then click "Probe Baseline Height". The head moves down until the electrode touches the substrate, records that height as the baseline, and lifts 1 mm. Then click "Set Geometric Area".

   "Probe Baseline Height" needs the ECRIT-HAT firmware and the power supply switched on, and the cell must be dry. While searching, the HAT drives the cell at 1 V behind a 10 mA limit and switches it off the moment current flows. The head moves down at 1 mm/s and stops the moment the HAT reports contact (it overshoots by about 0.2 mm), then backs off 0.5 mm and comes down again in 0.02 mm steps. On the rig this takes about 1 s per mm searched plus about 9 s, so start a few mm above the surface when you can. The `"probe"` settings in `config.json` change these numbers; `"speed": 0` there steps down 0.1 mm at a time instead of moving continuously (slower, about 3.7 s per mm).

   If it reports "No contact", the head went down `max_travel` mm (60 by default, in `config.json`'s `"probe"` settings) without current flowing: check that the electrode leads are connected. An open circuit looks exactly like empty space to the search, so the electrode may have been pressed into the substrate; lower `max_travel` to a few mm more than the gap you expect.

   To set the baseline by hand instead, jog the electrode until it just touches and click "Set Baseline Height": the head's current Z becomes the baseline.
4. If you have multiple geometric surface areas on the substrate and your objective is to perform rasterable electrodeposition, use the arrow buttons to position the electrode perpendicularly to the next geometric surface area and click "Set Geometric Area". Repeat the perpendicular position setting and the "Set Geometric Area" for all the surface areas on the substrate.
5. Click Next.
6. Select Voltage or Current Mode for constant current or contant voltage.

![](Screenshots/ParameterMenu.png)

7. The following experimental variables will be registered in the boxes (a) Input values for the distance between electrode and substrate (in millimeters). (b) The time the experiment should take at each point (in seconds). (c) Set either the current in milliAmperes or voltage in volts.

   For a three-electrode cell, tick "Use Reference Electrode" and connect the reference electrode to CN4. The run window then also shows the working electrode's potential against the reference ("WE vs RE"), the CSV gets a sixth column, "Potential WE vs RE" (V), and the plot gets a panel for it underneath. It needs the ECRIT-HAT firmware. A reading stuck at about -2.048 V means the reference input is open. Leave the box unticked for a two-electrode cell; the CSV then has the usual five columns. `"reference_electrode": true` in `config.json` ticks it by default, and on the command line it is `run --ref` or `ref on` in the shell.
8. Click "START ELECTROPLATING"
9. Wait for the experiment to start and monitor the real-time results.

![](Screenshots/ActiveExperimentMenu.png)

![Clockwise Pattern Rasterable Electrodeposition Video](/assets/ClockwisePatternRasterableElectrodeposition.mp4)

## License 
- Bruce Research Group
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
