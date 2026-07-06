import json
import sys 
import serial
import serial.tools.list_ports
from tkinter import messagebox

global ports
ports = serial.tools.list_ports.comports()

global can_start
can_start = False
# for p in ports:
#     print(p.device)
global options,config

#defining option keys
OPTIONS_PRINTER = "printer_port"
OPTIONS_ARDUINO = "arduino_port"
OPTIONS_CSV = "csv_filepath"

DATA_CURRENT = "Current"
DATA_TARGET_VOLTAGE = "Target Voltage"
DATA_ACTUAL_VOLTAGE = "Actual Voltage"
DATA_IND_TIME = "Time Individual"
DATA_TOTAL_TIME = "Time Accumulative"

def check_options(dictionary):
    all_options = [OPTIONS_ARDUINO,OPTIONS_CSV,OPTIONS_PRINTER]
    for opt in all_options:
        if opt not in dictionary.keys():
            dictionary.update({opt:""})
    with open("options.json","w") as f:
        json.dump(dictionary,f,ensure_ascii=False, indent=4)


# Load configuration from config.json
with open('config.json', 'r') as f:
    config = json.load(f)

try:
    # Load settings from options.json
    with open("options.json","r") as f:
        options = dict(json.load(f))
except FileNotFoundError as e:
    print(e)
    print("Creating options.json file...")
    with open("options.json","w") as f:
        placeholder = {OPTIONS_ARDUINO:"",OPTIONS_PRINTER:"",OPTIONS_CSV:""}
        json.dump(placeholder,f,ensure_ascii=False, indent=4)
    with open("options.json","r") as f:
        options = dict(json.load(f))
    print("Successfully Create!")
finally:
    check_options(options)

global arduino_port,printer_port, csv_filepath

#saving options for future use
arduino_port = options[OPTIONS_ARDUINO]
printer_port = options[OPTIONS_PRINTER]
csv_filepath = options[OPTIONS_CSV]

arduino_port = None
printer_port = None

def Clear_SerialStream(serial_obj):
    serial_obj.reset_output_buffer()
    serial_obj.reset_input_buffer()

def showcase_text(txt,symbol = "="):
    symbol_str = 3*len(txt)*symbol
    print()
    print(symbol_str)
    print(len(txt)*" "+txt)
    print(symbol_str)
    print()

def attempt_auto_connect():
    global arduino_port,printer_port,can_start
    for port in ports:
        if arduino_port != None and printer_port!= None:
            can_start = True
            return True
        port = port.name
        for baud in serial.Serial.BAUDRATES:
            if baud < 9600 or baud > 250000:
                continue
            try:
                test_ser = serial.Serial(port,baud,timeout=0.1,write_timeout=0.1)
                if test_ser.is_open == False:
                    test_ser.open()
                else:
                    Clear_SerialStream(test_ser)
                    test_ser.close()
                    test_ser.open()
                if arduino_port == None:
                    # Add to check if arduino is waiting to connect to the PSU and tell the user to turn it on and restart the program
                    test_ser.write(("r\n").encode())
                    output = test_ser.readline().decode()
                    if output == "":
                        continue
                    print(f"Output from port: {port}\nAt baudrate: {baud}\nArduino Output: {output}")
                    if output.__eq__("Reset\r\n"):
                        arduino_port = port
                        Clear_SerialStream(test_ser)
                        test_ser.close()
                        showcase_text("Made Connection to Arduino!")
                        break
                    if output.__eq__("PSU not Connected\r\n"):
                        Connection_Error("Ensure Power Supply is turned on and connected to the Arduino.")
                if printer_port == None:
                    test_ser.write(("M300 P100\r\n").encode())
                    output = test_ser.readline().decode()
                    if output == "":
                        continue
                    print(f"Output from port: {port}\nAt baudrate: {baud}\nPrinter Output: {output}")
                    if output.__eq__("ok\n"):
                        printer_port = port
                        Clear_SerialStream(test_ser)
                        test_ser.close()
                        showcase_text("Made Connection to 3D Printer!")
                        break
                print(f"closing port: {port}")
                test_ser.close()


            # except FileNotFoundError as e:
            #     print("Received File Not Found!")
            except serial.SerialException as e:
                print(f"Found no device on port: {port} at baudrate: {baud}")
                print(f"Exception: {e}")
                continue
            except Exception as e:
                print(f"Received Exception on port: {port} at baudrate: {baud}")
                print(f"Exception: {e}")
                continue
            finally:
                try:
                    test_ser.close()
                except Exception as e:
                    print(f"Received Exception: {e}")
    if arduino_port != None and printer_port!= None:
        can_start = True
        return True
    return False
            # check port for connection
            # Have selectport compare arduino and printer port to show user when selecting ports
            # if arduino and printer are found then return




global new_exp
new_exp = True



# print(f"options: {options}")
# print(f"csv file path: {csv_filepath}")

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
arduino = serial.Serial(baudrate=9600,timeout=0.1,write_timeout=0.1)
printer = serial.Serial(baudrate=115200,timeout=0.1,write_timeout=0.1)

csvdata = {
			'Current':[],
			'Target Voltage':[],
			'Actual Voltage':[],
			'Time Individual':[],
			'Time Accumulative':[]
		}

def update_options():
    global arduino_port,printer_port,csv_filepath
    with open("options.json","r") as f:
        options = json.load(f)
    # Arduino serial port
    arduino_port = options[OPTIONS_ARDUINO]
    # Printer serial port
    printer_port = options[OPTIONS_PRINTER]

    csv_filepath = options[OPTIONS_CSV]

def find_baudrate(serial_obj):
    baudrates = [9600,115200]
    for baud in baudrates:
        serial_obj.baudrate = baud
        serial_obj.write(("r\n").encode())
        serial_output = serial_obj.read()
        # print(f"repr baudrate output: {serial_output}")
        if serial_output != b'':
            print(f"Found baudrate at {baud}!")
            serial_obj.reset_output_buffer()
            serial_obj.reset_input_buffer()
            return
    Connection_Error("Could not identify the baudrate")
    
    

def open_ports():
    global can_start
    #Sets the port for the arduino and printer serial objs
    arduino.port = arduino_port
    printer.port = printer_port
    
    #Intialize flag to check if arduino or printer are connected
    arduino_flag = False
    printer_flag = False

    try:
        arduino.open()
        printer.open()
        print("Ports are open.")
        
        #searches avaiable baudrates and confirms the serial objects are connected to the right baudrates
        print("Scanning for arduino's baudrate...")
        find_baudrate(arduino)
        print("Scanning for printer's baudrate...")
        find_baudrate(printer)
        print()

        arduino.write(("r\n").encode()) #Sends reset command to arduino to confirm connection
        print("Sent test byte to arduino...")
        arduino_output = arduino.readline().decode()
       
        print(f"Output from Arduino: {arduino_output}")

        if arduino_output.__eq__("Reset\r\n"):
            print("Confirmed connection to arduino.")
            arduino_flag = True
        else:
            Connection_Error("Could not establish connection with Arduino.")
        # print(f"repr arduino output: '{repr(arduino_output)}'")
        print()


        printer.write(("M300 P100\n").encode())
        print("Sent test byte to printer...")
        printer_output = printer.readline().decode()
        if printer_output.__eq__("ok\n"):
            print("Confirmed connection to printer")
            printer_flag = True
        else:
            Connection_Error("Could not confirm connection to 3D Printer") #might want to make specific to issue connecting to printer or other device
        # print(f"repr printer output: '{repr(printer_output)}'")
        print()

        if arduino_flag == True and printer_flag == True:
            printer.write(("M117 " + "Running ECRIT Application...\n").encode())
            can_start = True

    except Exception as e:
        print("Could not open ports.")
        print(f"Received Error: {e}")
        print("Also check that PSU is turned on.")
        can_start = False
        # sys.exit()

def Connection_Error(exception_msg):
    messagebox.showerror(title="Can't Start Program",message="Could not communicate with connected devices.\nTry swapping the assigned ports for the arduino and printer ports.")
    raise Exception(exception_msg)

def Disp_Error(msg):
    messagebox.showerror(title="Can't Start Program",message=msg)

def get_start():
    return can_start

def are_open():
    
    return (arduino.is_open == True and printer.is_open==True)

if __name__ == "__main__":
    attempt_auto_connect()
    print(f"Arduino = {arduino_port}")
    print(f"Printer = {printer_port}")
