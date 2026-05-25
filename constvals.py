import json 
import serial
import serial.tools.list_ports


ports = serial.tools.list_ports.comports()
for p in ports:
    print(p.device)
global options,config

# Load configuration from config.json
with open('config.json', 'r') as f:
    config = json.load(f)

try:
    # Load settings from options.json
    with open("options.json","r") as f:
        options = json.load(f)
except FileNotFoundError as e:
    print(e)
    print("Creating options.json file...")
    with open("options.json","w") as f:
        placeholder = {"arduino_port":"","printer_port":""}
        json.dump(placeholder,f,ensure_ascii=False, indent=4)
    with open("options.json","r") as f:
        options = json.load(f)
    print("Successfully Create!")





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

global arduino,printer
arduino = serial.Serial(baudrate=9600)
printer = serial.Serial(baudrate=115200)


# arduino = serial.Serial(arduino_port, 9600)
# printer = serial.Serial(printer_port, 115200)

csvdata = {
			'Current':[],
			'Target Voltage':[],
			'Actual Voltage':[],
			'Time Individual':[],
			'Time Accumulative':[]
		}

def update_ports():
    global arduino_port,printer_port
    with open("options.json","r") as f:
        options = json.load(f)
    # Arduino serial port
    # arduino_port = "/dev/ttyACM0"
    arduino_port = options["arduino_port"]
    # Printer serial port
    # printer_port = "/dev/ttyUSB0"
    printer_port = options["printer_port"]

def open_ports():
    arduino.port = arduino_port
    printer.port = printer_port

    try:
        arduino.open()
        printer.open()
    except:
        print("Could not open port.")
        quit

def are_open():
    return (arduino.is_open == True and printer.is_open==True)
