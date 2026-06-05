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
3. To run the gui and to view it, run the following command in the terminal or open "SendCommandSerial.py" through the file explorer
```bash
./SendCommandSerial.py
```

### Set Up Arduino
1. Open the arduino IDE
2. Click File
3. Click Open File and find the cloned repository from the UI setup.
4. Open the Eletroplating_Serial_R4 folder and open the "Electroplating_Serial_R4.ino" file within
5. After the file opens, select the arduino board and upload the code to the board. For further information on how to do so use the guide linked [here](https://support.arduino.cc/hc/en-us/articles/4733418441116-Upload-a-sketch-in-Arduino-IDE)

## Usage
- A GUI to conduct electroplating experiments easily
- A analysis-tool for quick access to experiment data / information

1. Upon starting the program you are presented with the following start menu. To begin click "Configure Ports" to open the ports selection menu.

![](/Screenshots/StartMenu.png)

2. Click the dropdown to select your corresponding arduino and 3D printer ports. Then click the confirm button to complete the port selection. After successfully updating your ports, click the "Start" button on the start menu.

![](Screenshots/PortMenu.png)

3. If successful, the program will open to the controller menu. Here start by clear any possible obstructions out of the way of your 3D printer, then click the home button to ensure your printer starts at the right position.

The up and down arrows labeled "z-axis" are used to move the printer head up and down. The "y-axis controls forwards and backwards and the "x-axis controls left and right. You can use the options to the left of the arrows to choose how far the printer head moves on each click of the arrows.

![](Screenshots/ControllerMenu.png)

4. Now use the arrow buttons to position the probe attached to the printer head just a few millimeters above the cell, then click "Set Baseline Height".
5. Position the probe over one of your points and click "Set Geometric Area". Repeat this step until you have not points left to run your experiment on.
6. Click Next
7. Select Voltage or Current Mode

![](Screenshots/ParameterMenu.png)

8. Input values for the distance between ??? and ??? (in millimeters), The time the experiment should take at each point (in seconds), set either the current in milliAmperes or voltage in volts.
9. Click "START ELECTROPLATING"
10. Wait for the experiment to start and monitor the real-time results.

![](Screenshots/ActiveExperimentMenu.png)

## License 
- Bruce Research Group
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)