#import requests
import time
import serial
import math

# =========
# settings

# Arduino serial port
arduino_port = "/dev/ttyACM0"
# Printer serial port
printer_port = "/dev/ttyUSB0"

# mode (True for current, False for voltage)
current_mode = True
# target current in mA
target_current = 63
# target voltage in V
target_voltage = 5
# target duration in seconds
duration = 10
# distance between anode and cathode in mm
diff_z = 1

# machine limits
travel_z = 110.0
max_z = 50
min_z = 45.9
max_y = 142.0
min_y = 110.0
max_x = 160.0
min_x = 129.0

# single point mode
single_point = False

# number of points on each circle
points = 3
# distance between the radius of each circle
inc_r = 2

# =========

# find the actual min_z
min_z = min_z + diff_z
# find the middle
cx = min_x + (max_x - min_x) / 2
cy = min_y + (max_y - min_y) / 2

# cx cy override
cx = 146
cy = 124

# find the diameter
d = min(max_x - min_x, max_y - min_y)
# find the angle between each points
inc_theta = 360.0 / points

# connections
arduino = serial.Serial(arduino_port, 9600)
print("Serial connected to", arduino.name)

printer = serial.Serial(printer_port, 115200)
print("Printer connected to", printer.name)
time.sleep(5)

# function definitions

def arduino_write(command):
	arduino.write((command + "\n").encode())

def printer_write(command):
	printer.write((command + "\n").encode())

def move_head(x = None, y = None, z = None):
	command = "G1"
	if x is not None:
		command += " X" + str(x)
	if y is not None:
		command += " Y" + str(y)
	if z is not None:
		command += " Z" + str(z)

	printer_write(command)

def show_state(state):
	printer_write("M117 " + state)
	print(state)

def play_sound():
	commands = [
			"M300 P150 S196",
			"M300 P134 S262",
			"M300 P138 S330",
			"M300 P138 S392",
			"M300 P133 S523",
			"M300 P139 S659",
			"M300 P410 S784",
			"M300 P411 S659",
			"M300 P152 S208",
			"M300 P134 S262",
			"M300 P138 S311",
			"M300 P138 S415",
			"M300 P133 S523",
			"M300 P139 S622",
			"M300 P410 S831",
			"M300 P411 S622",
			"M300 P152 S233",
			"M300 P134 S294",
			"M300 P138 S349",
			"M300 P138 S466",
			"M300 P133 S587",
			"M300 P139 S698",
			"M300 P410 S932",
			"M300 P137 S932",
			"M300 P133 S932",
			"M300 P140 S932",
			"M300 P834 S1047"
		]

	for command in commands:
		printer_write(command)

try:
	# send reset command to arduino
	arduino_write("r")

	# set the printer to absolute mode
	printer_write("G90")

	# log file
	filename = "log_" + time.strftime("%Y%m%d-%H%M%S") + ".txt"
	f = open(filename, "w")
	f.write("Staring Time " + str(time.time()) + "\n")
	# log settings
	f.write("current_mode " + str(current_mode) + "\n")
	f.write("target_current " + str(target_current) + "\n")
	f.write("target_voltage " + str(target_voltage) + "\n")
	f.write("duration " + str(duration) + "s\n")
	f.write("diff_z " + str(diff_z) + "mm\n")
	f.write("points " + str(points) + "\n")
	f.write("inc_r " + str(inc_r) + "mm\n")
	f.write("====================================\n")

	# move the head to the travel height
	move_head(z=travel_z)
	show_state("To travel height")
	time.sleep(40)

	# move the head to the center of the circle
	move_head(x=cx, y=cy)
	show_state("Centering")
	time.sleep(5)

	# move the head to the right height
	move_head(z=max_z)
	show_state("To starting height")
	time.sleep(30)

	# points
	points = []
	if single_point:
		points.append((cx, cy))
	else:
		# polar coord
		r = inc_r
		theta = 0

		while True:
			# if we finished one circle, move the radius out to begin the next circle
			if theta >= 360:
				theta = 0
				r = r + inc_r

			# if we are at the outer most circle, stop the loop
			if r > d/2:
				break

			# convert polar to cartesian
			x = cx + r * math.cos(math.radians(theta))
			y = cy + r * math.sin(math.radians(theta))

			points.append((x,y))

			# increase the angle
			theta = theta + inc_theta

	# start the loop
	for (x, y) in points:

		# log the point
		point_str = "x: " + "{:.3f}".format(x) + ", y: " + "{:.3f}".format(y)
		f.write("\n" + point_str + "\n")
		show_state(point_str)

		# move the head to calculated position
		move_head(x=x, y=y)
		time.sleep(1)

		# move the head down
		move_head(z=min_z)
		time.sleep(2)

		# signal the arduino to start electroplating
		if current_mode:
			arduino_write("c " + str(target_current))
		else:
			arduino_write("v " + str(target_voltage))
		print("on")

		# record the start time so we know how long it has been
		start = time.time()
		while time.time() - start < duration: # loop until time has reached the set duration
			l = arduino.readline().decode()
			print(l, end="")
			f.write(l)

		# signal the arduino to stop electroplating
		arduino_write("f")
		print("off")
		time.sleep(0.5)

		# move the head up
		move_head(z=max_z)
		time.sleep(2)

	# We are done with the loop
	move_head(z=travel_z)
	play_sound()

# if Ctrl-C detected quit gracefully
except KeyboardInterrupt:
	print("Ctrl-C detected, quitting")
	# Stop the electroplating and move the head to travel height
	arduino_write("f")
	move_head(z=travel_z)

finally:
	show_state("Done")
	arduino.close()
	printer.close()
	f.close()
