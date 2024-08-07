#import requests
import time
import serial
import serial.tools.list_ports
import math
import tkinter as tk
from tkinter import ttk
import threading
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import json
import pandas as pd

# =========

ports = serial.tools.list_ports.comports()
for p in ports:
	print(p.device)

# Load configuration from config.json
with open('config.json', 'r') as f:
    config = json.load(f)

# settings

# Arduino serial port
arduino_port = "/dev/ttyACM0"
# Printer serial port
printer_port = "/dev/ttyUSB0"

# Matplotlib Graph
# style.use('fivethirtyeight')

# fig = plt.figure()
# ax1 = fig.add_subplot(111)

# mode (True for current, False for voltage)
current_mode = config["current_mode"]
# target current in mA
target_current = config["target_current"]
# target voltage in V
target_voltage = config["target_voltage"]
# target duration in seconds
duration = config["duration"]
# distance between anode and cathode in mm
diff_z = config["diff_z"]

# machine limits
travel_z = config["travel_z"]
max_z = 55.0
min_z = config["min_z"]
mac_z = 45.9
max_y = 142.0
min_y = 110.0
max_x = 160.0
min_x = 129.0

x_limit = config["x_limit"]
y_limit = config["y_limit"]
z_limit = config["z_limit"]

# current pos
pos_x = config["pos_x"]
pos_y = config["pos_y"]
pos_z = config["pos_z"]

# center x,y
cen_x = config["cen_x"]
cen_y = config["cen_y"]

# target z
tar_z = config["tar_z"]

# single point mode
single_point = config["single_point"]

# number of points on each circle
points = config["points"]
# distance between the radius of each circle
inc_r = config["inc_r"]

# points
points_coordinates = []
# =========

# find the actual min_z
# min_z = min_z + diff_z
# find the middle
# cx = min_x + (max_x - min_x) / 2
# cy = min_y + (max_y - min_y) / 2

# # cx cy override
# cx = 146
# cy = 124

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
	print("target z set")

def set_distance_position():
	global diff_z, tar_z, min_z
	diff_z = float(input_distance.get(1.0, "end-1c"))
	min_z = tar_z + diff_z
	print("Distance Updated")
	
def set_duration_time():
	global duration
	duration = float(input_duration.get(1.0, "end-1c"))
	print("Duration Updated")

def set_current_target():
	global target_current
	target_current = float(input_current.get(1.0, "end-1c")) # Need to figure out how to update this live during electroplating
	# arduino_write("c " + str(target_current))
	# readSerial()
	print("Current Updated to", target_current)

def set_voltage_target():
	global target_voltage
	target_voltage = float(input_voltage.get(1.0, "end-1c")) # Need to figure out how to update this live during electroplating
	# arduino_write("c " + str(target_current))
	# readSerial()
	print("Voltage Updated to", target_voltage)

def set_point_mode():
	global single_point, points_coordinates
	if single_point:
		set_point.config(text="Single Point OFF", relief="raised")
		set_point1.grid(row=10, column=8, padx=5, pady=5)
		points_label.config(text=f'{len(points_coordinates)} points set')
	else:
		set_point.config(text="Single Point ON", relief="sunken")
		set_point1.grid_forget()
		points_label.config(text="Using Center point")
		points_coordinates = []
	single_point = not single_point

def set_mode_electroplating():
	global current_mode
	if current_mode:
		set_mode.config(text="Voltage Mode", relief="raised")
	else:
		set_mode.config(text="Current Mode", relief="sunken")
	current_mode = not current_mode

def set_a_point():
	global points_coordinates, pos_x, pos_y
	points_coordinates.append((pos_x, pos_y))
	points_label.config(text=f'{len(points_coordinates)} points set')
	print("point set at", pos_x, pos_y)

def readSerial():
	l = arduino.readline().decode()
	print("this is what readSerial is printing", l, end="")

def animate(i):
	global vol_list, time_list
	ax1.clear()
	ax1.plot(vol_list, time_list)

def do_task():
	threading.Thread(target=start_electroplating, args=()).start()

def start_electroplating():
	global points_coordinates, vol, tar_vol, cur
	try:
		# send reset command to arduino
		arduino_write("r")
		readSerial()

		# set the printer to absolute mode
		printer_write("G90")

		# log file, csv file
		csvdata = {
			'Current':[],
			'Target Voltage':[],
			'Actual Voltage':[],
			'Time Individual':[],
			'Time Accumulative':[]
		}
		
		filename = "log_" + time.strftime("%Y%m%d-%H%M%S") + ".txt"
		csvname = "log_" + time.strftime("%Y%m%d-%H%M%S") + ".csv"
		f = open(filename, "w")
		f.write("Staring Time " + str(time.time()) + "\n")
		# log settings
		f.write("current_mode " + str(current_mode) + "\n")
		f.write("target_current " + str(target_current) + "\n")
		f.write("target_voltage " + str(target_voltage) + "\n")
		f.write("duration " + str(duration) + "s\n")
		f.write("diff_z " + str(diff_z) + "mm\n")
		f.write("points " + str(len(points_coordinates)) + "\n")
		f.write("inc_r " + str(inc_r) + "mm\n")
		f.write("====================================\n")

		# move the head to the travel height
		move_head(z=travel_z)
		show_state("To travel height")
		time.sleep(40)

		# move the head to the center of the circle
		move_head(x=cen_x, y=cen_y)
		show_state("Centering")
		time.sleep(5)

		# move the head to the right height
		move_head(z=max_z)
		show_state("To starting height")
		time.sleep(30)


		if single_point:
			points_coordinates = [(cen_x, cen_y)]
		# else:
		# 	# polar coord
		# 	r = inc_r
		# 	theta = 0

		# 	while True:
		# 		# if we finished one circle, move the radius out to begin the next circle
		# 		if theta >= 360:
		# 			theta = 0
		# 			r = r + inc_r

		# 		# if we are at the outer most circle, stop the loop
		# 		if r > d/2:
		# 			break

		# 		# convert polar to cartesian
		# 		x = cx + r * math.cos(math.radians(theta))
		# 		y = cy + r * math.sin(math.radians(theta))

		# 		points.append((x,y))

		# 		# increase the angle
		# 		theta = theta + inc_theta

		i=-1
		# start the loop
		for (x, y) in points_coordinates:
			i+=1

			# csv space
			csvdata['Current'].append("")
			csvdata['Target Voltage'].append("")
			csvdata['Actual Voltage'].append("")
			csvdata['Time Individual'].append("")
			csvdata['Time Accumulative'].append("")

			# log the point
			point_str = "x: " + "{:.3f}".format(x) + ", y: " + "{:.3f}".format(y)
			f.write("\n" + point_str + "\n")
			show_state(point_str)

			# move the head to calculated position
			move_head(x=x, y=y)
			time.sleep(10)

			# move the head down
			move_head(z=min_z)
			time.sleep(20)

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
				f.write(l + "," + str(time.time()-start) + "\n")
				values = l.split(',')
				print("this is values:", values)
				cur = values[0]
				tar_vol = values[1]
				vol = values[2]
				csvdata['Current'].append(float(cur))
				csvdata['Target Voltage'].append(float(tar_vol))
				csvdata['Actual Voltage'].append(float(vol))
				csvdata['Time Individual'].append(float(time.time()-start))
				csvdata['Time Accumulative'].append(float(time.time()-start)+ i*duration)
				cur_label.config(text=f'current: {cur}')
				vol_label.config(text=f'voltage: {vol}')
				tar_vol_label.config(text=f'target voltage: {tar_vol}')
				vol_list.append(float(vol))
				time_list.append(float(time.time()-start))
				time_remaining_label.config(text=f"time left: {int(duration+start-time.time())}")

			# signal the arduino to stop electroplating
			arduino_write("f")
			readSerial()
			readSerial()
			print("off")
			time.sleep(0.5)

			# move the head up
			move_head(z=max_z)
			time.sleep(10)

		# We are done with the loop
		move_head(z=travel_z)
		# play_sound()

	# if Ctrl-C detected quit gracefully
	except KeyboardInterrupt:
		print("Ctrl-C detected, quitting")
		# Stop the electroplating and move the head to travel height
		move_head(z=travel_z)

	finally:
		df = pd.DataFrame(csvdata)
		df.to_csv(csvname, index=False)
		arduino_write("f")
		show_state("Done")
		arduino.close()
		printer.close()
		f.close()

# gui
m = tk.Tk()
m.configure(background='#2E3440')
m.title('Electroplating GUI')
style = ttk.Style()
style.configure('TButton',
                font=('Helvetica', 12),
                padding=6,
                foreground='#FFFFFF',
                background='#4CAF50', # Green background color
                borderwidth=0)
style.map('TButton',
          foreground=[('pressed', '#FFFFFF'), ('active', '#FFFFFF'), ('!disabled', '#FFFFFF')],
          background=[('pressed', '#388E3C'), ('active', '#45A049'), ('!disabled', '#4CAF50')])
style.configure('TLabel',
								font=('Helvetica', 12),
								foreground='#FFFFFF',
								background = '#2E3440')
style.configure('TRadiobutton',
								font=('Helvetica', 12),
								foreground='#FFFFFF',
								background = '#2E3440')
style.configure('TFrame', background='#2E3440')
tabControl = ttk.Notebook(m)
tab1 = ttk.Frame(tabControl) 
tab2 = ttk.Frame(tabControl)
tab3 = ttk.Frame(tabControl)
tab4 = ttk.Frame(tabControl)
tab1.configure(style='TFrame')
tab2.configure(style='TFrame')
tab3.configure(style='TFrame')
tab4.configure(style='TFrame')
tabControl.add(tab1, text ='System Calibration') 
tabControl.add(tab2, text ='Operational Parameter Settings')
tabControl.add(tab3, text ='Starting Experiment') 
tabControl.add(tab4, text ='Experimental Data Analysis')
tabControl.pack(expand = 1, fill ="both") 

# values
cur = "current: no reading yet"
vol = "actual voltage: no reading yet"
tar_vol = "target voltage: no reading yet"
vol_list = []
time_list = []

# homing function
homing = ttk.Button(tab1, text='Home', style='TButton',width=5, command=lambda : head_home()) ; homing.grid(row = 1, column = 1)

# setting increment
increment = tk.DoubleVar(None, 1.0)
increment_options = (('0.1', 0.1), ('1', 1.0), ('10', 10.0), ('100', 100.0))

increment_label = ttk.Label(tab1, text="Input the Increment Size:", style='TLabel')
increment_label.grid(row = 3, column = 0, padx=5, pady=5)
i=4
for increments in increment_options:
    r = ttk.Radiobutton(
        tab1,
        text=increments[0],
        value=increments[1],
				style='TRadiobutton',
        variable=increment
    )
    r.grid(row = i, column = 0, sticky='w', padx=5, pady=5)
    i+=1

#movement functions
up = tk.Button(tab1, text='↑', width=2, command=lambda : move_z(increment.get()))
up.grid(row=4, column=7, padx=20, pady=5)
down = tk.Button(tab1, text='↓', width=2, command=lambda : move_z(-increment.get()))
down.grid(row=6, column=7, padx=20, pady=5)
z_label = ttk.Label(tab1, text="z-axis", style='TLabel')
z_label.grid(row = 7, column = 7, padx=5, pady=5)
left = tk.Button(tab1, text='←', width=2, command=lambda : move_x(-increment.get()))
left.grid(row=5, column=3, padx=5, pady=5)
right = tk.Button(tab1, text='→', width=2, command=lambda : move_x(increment.get()))
right.grid(row=5, column=5, padx=5, pady=5)
y_label = ttk.Label(tab1, text="x-axis", style='TLabel')
y_label.grid(row = 5, column = 2, padx=5, pady=5)
forward = tk.Button(tab1, text='↑', width=2, command=lambda : move_y(-increment.get()))
forward.grid(row=4, column=4, padx=5, pady=5)
back = tk.Button(tab1, text='↓', width=2, command=lambda : move_y(increment.get()))
back.grid(row=6, column=4, padx=5, pady=5)
x_label = ttk.Label(tab1, text="y-axis", style='TLabel')
x_label.grid(row = 7, column = 4, padx=5, pady=5)
set_center = tk.Button(tab1, text='SET CENTER', width=20, command=lambda : set_center_position()) ; set_center.grid(row=8, column=1, padx=5, pady=5)
move_to_center = tk.Button(tab1, text='MOVE TO CENTER', width=20, command=lambda : move_head(x=cen_x, y=cen_y)) ; move_to_center.grid(row=9, column=1, padx=5, pady=5)
set_target_z = tk.Button(tab1, text='SET SURFACE Z', width=20, command=lambda : set_target_z_position()) ; set_target_z.grid(row=10, column=1, padx=5, pady=5)
move_to_target_z = tk.Button(tab1, text='MOVE TO SURFACE Z', width=20, command=lambda : move_head(z=tar_z)) ; move_to_target_z.grid(row=11, column=1, padx=5, pady=5)
set_point = tk.Button(tab1, text='Single Point ON', width=20, relief='sunken', command=lambda : set_point_mode()) ; set_point.grid(row=8, column=8, padx=5, pady=5)
set_point1 = tk.Button(tab1, text='SET Point', width=20, command=lambda : set_a_point())
points_label = ttk.Label(tab1, text="Using Center point", style='TLabel')
points_label.grid(row = 9, column = 8, padx=5, pady=5)
set_mode = tk.Button(tab1, text='Current Mode', width=20, relief='sunken', command=lambda : set_mode_electroplating()) ; set_mode.grid(row=11, column=8, padx=5, pady=5)

#Operational Parameters
distance_label = ttk.Label(tab2, text="Distance of WE from CE (mm):", style='TLabel')
distance_label.grid(row = 0, column = 0, sticky='w', padx=5, pady=5)
duration_label = ttk.Label(tab2, text="Electrodeposition time (sec):", style='TLabel')
duration_label.grid(row = 1, column = 0, sticky='w', padx=5, pady=5)
current_label = ttk.Label(tab2, text="Set a Current (mA):", style='TLabel')
current_label.grid(row = 2, column = 0, sticky='w', padx=5, pady=5)
voltage_label = ttk.Label(tab2, text="Set a Voltage (V):", style='TLabel')
voltage_label.grid(row = 3, column = 0, sticky='w', padx=5, pady=5)
input_distance = tk.Text(tab2, height=1, width=5) ; input_distance.grid(row=0, column=1, sticky='w', padx=5, pady=5)
input_duration = tk.Text(tab2, height=1, width=5) ; input_duration.grid(row=1, column=1, sticky='w', padx=5, pady=5)
input_current = tk.Text(tab2, height=1, width=5) ; input_current.grid(row=2, column=1, sticky='w', padx=5, pady=5)
input_voltage = tk.Text(tab2, height=1, width=5) ; input_voltage.grid(row=3, column=1, sticky='w', padx=5, pady=5)
set_distance = tk.Button(tab2, text='SET DISTANCE', width=20, command=lambda : set_distance_position()) ; set_distance.grid(row=0, column=2, padx=5, pady=5)
set_duration = tk.Button(tab2, text='SET DURATION', width=20, command=lambda : set_duration_time()) ; set_duration.grid(row=1, column=2, padx=5, pady=5)
set_current = tk.Button(tab2, text='SET CURRENT', width=20, command=lambda : set_current_target()) ; set_current.grid(row=2, column=2, padx=5, pady=5)
set_voltage = tk.Button(tab2, text='SET VOLTAGE', width=20, command=lambda : set_voltage_target()) ; set_voltage.grid(row=3, column=2, padx=5, pady=5)

#value display
cur_label = tk.Label(tab3)
cur_label.config(text=cur)
cur_label.grid(row=0, column=0, sticky='w', padx=5, pady=5)
vol_label = tk.Label(tab3)
vol_label.config(text=vol)
vol_label.grid(row=1, column=0, sticky='w', padx=5, pady=5)
tar_vol_label = tk.Label(tab3)
tar_vol_label.config(text=tar_vol)
tar_vol_label.grid(row=2, column=0, sticky='w', padx=5, pady=5)
time_remaining_label = tk.Label(tab3)
time_remaining_label.config(text="time left: no reading yet")
time_remaining_label.grid(row=3, column=0, sticky='w', padx=5, pady=5)

#electroplating functions
start = tk.Button(tab2, text='START ELECTROPLATING', width=20, command=lambda : do_task()) ; start.grid(row=4, column=2, sticky='w', padx=5, pady=5)
# ani = animation.FuncAnimation(fig, animate, interval=1000)
# plt.show()
m.mainloop()