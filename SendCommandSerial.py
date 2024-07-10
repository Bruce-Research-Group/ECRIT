#import requests
import time
import serial
import serial.tools.list_ports
import math
import tkinter as tk
from tkinter import ttk
import threading
# =========

ports = serial.tools.list_ports.comports()
for p in ports:
	print(p.device)

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

x_limit = 235
y_limit = 235
z_limit = 200

# current pos
pos_x = 0
pos_y = 0
pos_z = 0

# center x,y
cen_x = 146
cen_y = 124

# target z
tar_z = 90

# single point mode
single_point = True

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
	global pos_x, pos_y, pos_z
	command = "G1"
	if x is not None:
		command += " X" + str(x)
		pos_x = x
	if y is not None:
		command += " Y" + str(y)
		pos_y = y
	if z is not None:
		command += " Z" + str(z)
		pos_z = z
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

def head_home():
	global pos_x, pos_y, pos_z
	pos_x=0
	pos_y=0
	pos_z=0
	printer_write("G28")

def move_x(amount):
	global pos_x
	pos_x = min(x_limit, max(0, pos_x + amount))
	move_head(x=pos_x)

def move_y(amount):
	global pos_y
	pos_y = min(y_limit, max(0, pos_y + amount))
	move_head(y=pos_y)

def move_z(amount):
	global pos_z
	pos_z = min(z_limit, max(0, pos_z + amount))
	move_head(z=pos_z)

def set_center_position():
	global pos_x, pos_y, cen_x, cen_y
	cen_x = pos_x
	cen_y = pos_y

def set_target_z_position():
	global pos_z, tar_z
	tar_z = pos_z

def readSerial():
	l = arduino.readline().decode()
	print(l, end="")

def do_task():
	threading.Thread(target=start_electroplating, args=()).start()

def start_electroplating():
	global points, vol, tar_vol, cur
	try:
		# send reset command to arduino
		arduino_write("r")
		readSerial()

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
		#time.sleep(40)

		# move the head to the center of the circle
		move_head(x=cx, y=cy)
		show_state("Centering")
		#time.sleep(5)

		# move the head to the right height
		move_head(z=max_z)
		show_state("To starting height")
		#time.sleep(30)

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
				readSerial()
			else:
				arduino_write("v " + str(target_voltage))
				readSerial()
			print("on")

			# record the start time so we know how long it has been
			start = time.time()
			while time.time() - start < duration: # loop until time has reached the set duration
				l = arduino.readline().decode().strip()
				print(l)
				f.write(l + "\n")
				values = l.split(',')
				cur = values[0]
				cur_label.config(text=f'current: {cur}')
				vol_label.config(text=f'voltage: {vol}')
				tar_vol_label.config(text=f'target voltage: {tar_vol}')
				tar_vol = values[1]
				vol = values[2]

			# signal the arduino to stop electroplating
			arduino_write("f")
			print("off")
			time.sleep(0.5)

			# move the head up
			move_head(z=max_z)
			time.sleep(2)

		# We are done with the loop
		move_head(z=travel_z)
		# play_sound()

	# if Ctrl-C detected quit gracefully
	except KeyboardInterrupt:
		print("Ctrl-C detected, quitting")
		# Stop the electroplating and move the head to travel height
		move_head(z=travel_z)

	finally:
		arduino_write("f")
		show_state("Done")
		arduino.close()
		printer.close()
		f.close()

# gui
m = tk.Tk()
m.title('Electroplating GUI')

# values
cur = "current: no reading yet"
vol = "voltage: no reading yet"
tar_vol = "target voltage: no reading yet"

# homing function
homing = tk.Button(m, text='Home', width=5, command=lambda : head_home()) ; homing.pack()

# setting increment
increment = tk.DoubleVar(None, 1.0)
increment_options = (('0.1', 0.1), ('1', 1.0), ('10', 10.0), ('100', 100.0))

increment_label = ttk.Label(text="increment size?")
increment_label.pack(fill='x', padx=5, pady=5)

for increments in increment_options:
    r = ttk.Radiobutton(
        m,
        text=increments[0],
        value=increments[1],
        variable=increment
    )
    r.pack(fill='x', padx=5, pady=5)

#movement functions
up = tk.Button(m, text='UP', width=5, command=lambda : move_z(increment.get())) ; up.pack()
down = tk.Button(m, text='DOWN', width=5, command=lambda : move_z(-increment.get())) ; down.pack()
left = tk.Button(m, text='LEFT', width=5, command=lambda : move_x(-increment.get())) ; left.pack()
right = tk.Button(m, text='RIGHT', width=5, command=lambda : move_x(increment.get())) ; right.pack()
forward = tk.Button(m, text='FORWARD', width=5, command=lambda : move_y(-increment.get())) ; forward.pack()
back = tk.Button(m, text='BACK', width=5, command=lambda : move_y(increment.get())) ; back.pack()
set_center = tk.Button(m, text='SET CENTER', width=20, command=lambda : set_center_position()) ; set_center.pack()
move_to_center = tk.Button(m, text='MOVE TO CENTER', width=20, command=lambda : move_head(x=cen_x, y=cen_y)) ; move_to_center.pack()
set_target_z = tk.Button(m, text='SET TARGET Z', width=20, command=lambda : set_target_z_position()) ; set_target_z.pack()
move_to_target_z = tk.Button(m, text='MOVE TO TARGET Z', width=20, command=lambda : move_head(z=tar_z)) ; move_to_target_z.pack()

#value display
cur_label = tk.Label(m)
cur_label.config(text=cur)
cur_label.pack()
vol_label = tk.Label(m)
vol_label.config(text=vol)
vol_label.pack()
tar_vol_label = tk.Label(m)
tar_vol_label.config(text=tar_vol)
tar_vol_label.pack()

#electroplating functions
start = tk.Button(m, text='START ELECTROPLATING', width=20, command=lambda : do_task()) ; start.pack()

m.mainloop()


