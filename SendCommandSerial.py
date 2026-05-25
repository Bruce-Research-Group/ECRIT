#import requests
import time
import serial
import serial.tools.list_ports
import math
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import json
import pandas as pd
import os
import shutil
import platform
import initUI
import SelectPort
import UtilUI
import constvals

global x_limit

# =========
def setup():
	ports = serial.tools.list_ports.comports()
	for p in ports:
		print(p.device)
	global options,config

	# Load configuration from config.json
	with open('config.json', 'r') as f:
		config = json.load(f)

	# Load settings from options.json
	with open("options.json","r") as f:
		options = json.load(f)

	# print("asking user if they want to update port")
	# #asks user if they want to select new port

def assignbasic_vals():
	# settings

	global arduino_port,printer_port

	# Arduino serial port
	# arduino_port = "/dev/ttyACM0"
	arduino_port = options["arduino_port"]
	# Printer serial port
	# printer_port = "/dev/ttyUSB0"
	printer_port = options["printer_port"]

	# Matplotlib Graph
	# style.use('fivethirtyeight')

	# fig = plt.figure()
	# ax1 = fig.add_subplot(111)

	global current_mode,target_current, target_voltage, duration, diff_z

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

	global min_z, max_z, min_y, max_y, max_x, min_x,travel_z
	# machine limits
	travel_z = config["travel_z"]
	min_z = config["min_z"]
	max_z = 45.9
	max_y = 142.0
	min_y = 110.0
	max_x = 160.0
	min_x = 129.0

	global x_limit, y_limit, z_limit
	x_limit = config["x_limit"]
	# print(f"x limit is: {x_limit}")
	y_limit = config["y_limit"]
	z_limit = config["z_limit"]

	global pos_x, pos_y, pos_z
	# current pos
	pos_x = config["pos_x"]
	pos_y = config["pos_y"]
	pos_z = config["pos_z"]

	global cen_x, cen_y
	# center x,y
	cen_x = config["cen_x"]
	cen_y = config["cen_y"]

	global tar_z, single_point, points, inc_r, points_coordinates
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

	global timestamp, filename, csvname
	# naming
	timestamp = ''
	filename = ''
	csvname = ''

	# =========

	# find the actual min_z
	# min_z = min_z + diff_z
	# find the middle
	# cx = min_x + (max_x - min_x) / 2
	# cy = min_y + (max_y - min_y) / 2

	# # cx cy override
	# cx = 146
	# cy = 124

	global d, inc_theta
	# find the diameter
	d = min(max_x - min_x, max_y - min_y)
	# find the angle between each points
	inc_theta = 360.0 / points

def confirmports():
	global arduino_port,printer_port
	global arduino,printer
	# connections
	# try:
	# 	arduino = serial.Serial(arduino_port, 9600)
	# 	print("Serial connected to", arduino.name)
	# 	# arduino.close()
	# except OSError as e:
	# 	print(e)
	# 	UtilUI.tooltip("Could not open arduino port! Please update selected port")
	# 	initUI.on_quit()
	# 	initUI.startprogram()
	# 	arduino_port = options["arduino_port"]
	# 	printer_port = options["printer_port"]
	# 	arduino = serial.Serial(arduino_port, 9600)
	# 	print("Serial connected to", arduino.name)
		

	# try:
	# 	printer = serial.Serial(printer_port, 115200)
	# 	print("Printer connected to", printer.name)
	# 	# printer.close()
	# except OSError as e:
	# 	print(e)
	# 	print("Could not open printer port! Please update selected port")
	# 	initUI.on_quit()
	# 	initUI.startprogram()
	# 	arduino_port = options["arduino_port"]
	# 	printer_port = options["printer_port"]
	# 	printer = serial.Serial(printer_port, 9600)
	# 	print("Printer connected to", printer.name)
	constvals.open_ports()

		
		
	time.sleep(5)

# function definitions

def arduino_write(command):
	constvals.arduino.write((command + "\n").encode())

def printer_write(command):
	constvals.printer.write((command + "\n").encode())

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

def move_head_center():
	move_confirm = messagebox.askokcancel(message="Move printer head to center?")
	if move_confirm:
		move_head(x=cen_x, y=cen_y)
	# tk.Message(text="Move printer head to center?",)

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

def set_distance_position(input_distance):
	global diff_z, tar_z, min_z
	# print(repr(input_distance.get("1.0","end-1c")))
	if input_distance.get("1.0","end-1c") == "":
		messagebox.showerror(message="Please input proper distance value that contains no symbols or letters aside from '.' and numbers.")
		return False
	diff_z = float(input_distance.get(1.0, "end-1c"))
	min_z = tar_z + diff_z
	print("Distance Updated")
	return True
	
def set_duration_time(input_duration):
	global duration
	if input_duration.get("1.0","end-1c") == "":
		messagebox.showerror(message="Please input proper duration value that contains no symbols or letters aside from '.' and numbers.")
		return False
	duration = float(input_duration.get(1.0, "end-1c"))
	print(f"Duration Updated to {duration}")
	return True

def set_current_target(input_current):
	global target_current
	if input_current.get("1.0","end-1c") == "":
		messagebox.showerror(message="Please input proper current value that contains no symbols or letters aside from '.' and numbers.")
		return False
	target_current = float(input_current.get(1.0, "end-1c")) # Need to figure out how to update this live during electroplating
	# arduino_write("c " + str(target_current))
	# readSerial()
	print("Current Updated to", target_current)
	return True

def get_current_mode():
	return current_mode

def set_current_mode_val(val):
	global current_mode
	current_mode = val

def set_voltage_target(input_voltage):
	global target_voltage
	if input_voltage.get("1.0","end-1c") == "":
		messagebox.showerror(message="Please input proper voltage value that contains no symbols or letters aside from '.' and numbers.")
		return False
	target_voltage = float(input_voltage.get(1.0, "end-1c")) # Need to figure out how to update this live during electroplating
	# arduino_write("c " + str(target_current))
	# readSerial()
	print("Voltage Updated to", target_voltage)
	return True

def set_point_mode(set_point,set_point1,points_label):
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

def set_mode_electroplating(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label):
	global current_mode
	if current_mode:
		set_mode.config(text="Voltage Mode", relief="raised")

		input_current.delete('1.0', "end")
		
		input_current.config(state="disabled")
		set_current.config(state="disabled")
		current_label.config(state="disabled")

		input_voltage.config(state="normal")
		set_voltage.config(state="normal")
		voltage_label.config(state="normal")
		
	else:
		set_mode.config(text="Current Mode", relief="sunken")

		input_voltage.delete('1.0', "end")

		input_voltage.config(state="disabled")
		set_voltage.config(state="disabled")
		voltage_label.config(state="disabled")

		input_current.config(state="normal")
		set_current.config(state="normal")
		current_label.config(state="normal")
	current_mode = not current_mode

def set_current_mode(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label,set_volt,set_curr):
	set_current_mode_val(False)
	set_volt.config(bg="white")
	set_curr.config(bg="#b1c6eb")
	set_mode_electroplating(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label)


def set_voltage_mode(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label,set_volt,set_curr):
	set_current_mode_val(True)
	set_volt.config(bg="#b1c6eb")
	set_curr.config(bg="white")
	set_mode_electroplating(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label)


def set_a_point(points_label,undo_point):
	global points_coordinates, pos_x, pos_y
	if (pos_x,pos_y) not in points_coordinates:
		undo_point.config(state="normal")
		points_coordinates.append((pos_x, pos_y))
		points_label.config(text=f'{len(points_coordinates)} points set')
		print("point set at", pos_x, pos_y)
	else:
		print(f"A point is already set at ({pos_x},{pos_y})")

def undo_set_point(points_label,undo_point):
	if len(points_coordinates) == 0:
		print("No points to remove.")
		return
	print(f"point: {points_coordinates.pop()} removed!")
	points_label.config(text=f'{len(points_coordinates)} points set')
	if len(points_coordinates) == 0:
		points_label.config(text="0")
		undo_point.config(state="disabled")

		

def readSerial():
	l = constvals.arduino.readline().decode()
	print("Arduino:", l, end="")

def animate(i):
	global vol_list, time_list
	ax1.clear()
	ax1.plot(vol_list, time_list)

# def do_task():

# 	threading.Thread(target=start_electroplating, args=()).start()



def download_data():
	global csvname
	# Determine the default download folder based on the operating system
	if platform.system() == 'Windows':
			download_folder = os.path.join(os.environ['USERPROFILE'], 'Downloads')
	else:
			download_folder = os.path.join(os.environ['HOME'], 'Downloads')

	# Define the full path to save the file in the Downloads folder
	destination_path = os.path.join(download_folder, os.path.basename(csvname))

	# Copy the CSV file to the Downloads folder
	shutil.copy(csvname, destination_path)
	messagebox.showinfo(title="File Saved!",message=f"File downloaded to {destination_path}")
	print(f"File downloaded to {destination_path}")
	

def start_electroplating(cur_label,vol_label,tar_vol_label,time_remaining_label,vol_list,time_list):
	global points_coordinates, vol, tar_vol, cur, timestamp, filename, csvname,csvdata
	try:
		print(f"Ports are open: {constvals.are_open()}")
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
		
		timestamp = time.strftime("%Y%m%d-%H%M%S")
		filename = "log_" + timestamp + ".txt"
		csvname = "log_" + timestamp + ".csv"
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
		move_head(z=min_z+2)
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
			constvals.csvdata['Current'].append("")
			constvals.csvdata['Target Voltage'].append("")
			constvals.csvdata['Actual Voltage'].append("")
			constvals.csvdata['Time Individual'].append("")
			constvals.csvdata['Time Accumulative'].append("")

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
				l = constvals.arduino.readline().decode().strip()
				print(l)
				f.write(l + "," + str(time.time()-start) + "\n")
				values = l.split(',')
				# print(f"values: {values}\nl: {l}")
				if len(values) <3:
					continue
				cur = values[0]
				tar_vol = values[1]
				vol = values[2]
				constvals.csvdata['Current'].append(float(cur))
				constvals.csvdata['Target Voltage'].append(float(tar_vol))
				constvals.csvdata['Actual Voltage'].append(float(vol))
				constvals.csvdata['Time Individual'].append(float(time.time()-start))
				constvals.csvdata['Time Accumulative'].append(float(time.time()-start)+ i*duration)
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
			move_head(z=min_z+2)
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
		df = pd.DataFrame(constvals.csvdata)
		df.to_csv(csvname, index=False)
		arduino_write("f")
		show_state("Done")
		download_data()
		#arduino.close()
		#printer.close()
		f.close()

def halt_experiment():
	arduino_write("f")

# gui
def buildMainUI():
	UtilUI.startmainUI()
###

def get_config_val(val_name):
	with open('config.json', 'r') as f:
		config = json.load(f)
	return config[val_name]

def get_option_val(val_name):
	with open('options.json', 'r') as f:
		options = json.load(f)
	return options[val_name]

def get_printer():
	port = get_option_val("printer_port")
	ser = serial.Serial()
	ser.baudrate = 19200
	ser.port = port
	# ser.open()
	return ser

def get_arduino():
	port = get_option_val("arduino_port")
	ser = serial.Serial()
	ser.baudrate = 19200
	ser.port = port
	# ser.open()
	return ser

def main():
	#Basic Startup
	print("starting program...")
	initUI.startprogram()
	print("running setup...")
	setup()
	print("assigning configured values...")
	assignbasic_vals()
	# print(config)

	#Attempts to connect to ports and set printer to start position
	print("confirming ports...")
	confirmports() 
	print(f"Arduino Port is {constvals.arduino_port}\nPrinter Port is {constvals.printer_port}")
	# print(x_limit)

	#Launches Main Application Window
	print("Launching Application...")
	buildMainUI()

if (__name__ == "__main__"):
	main()
	# buildUI()
