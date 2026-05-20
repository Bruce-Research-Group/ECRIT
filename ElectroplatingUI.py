import tkinter as tk
from tkinter import ttk
from SendCommandSerial import *

def buildUI():
	global m
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
	# tabControl = ttk.Notebook(m)
	# tab1 = ttk.Frame(tabControl) 
	# tab2 = ttk.Frame(tabControl)
	# tab4 = ttk.Frame(tabControl)
	# tab1.configure(style='TFrame')
	# tab2.configure(style='TFrame')
	# tab4.configure(style='TFrame')
	# tabControl.add(tab1, text ='System Calibration') 
	# tabControl.add(tab2, text ='Operational Parameter Settings')
	# tabControl.add(tab4, text ='Experimental Data Analysis')
	# tabControl.pack(expand = 1, fill ="both")
	
	global cur,vol,tar_vol,vol_list,time_list
	# values
	cur = "current: no reading yet"
	vol = "actual voltage: no reading yet"
	tar_vol = "target voltage: no reading yet"
	vol_list = []
	time_list = []
	
	build_controllerUI()
	# # homing function
	# homing = ttk.Button(tab1, text='Home', style='TButton',width=5, command=lambda : head_home()) ; homing.grid(row = 1, column = 1)

	# # setting increment
	# increment = tk.DoubleVar(None, 1.0)
	# increment_options = (('0.1', 0.1), ('1', 1.0), ('10', 10.0), ('100', 100.0))

	# increment_label = ttk.Label(tab1, text="Input the Increment Size:", style='TLabel')
	# increment_label.grid(row = 3, column = 0, padx=5, pady=5)
	# i=4
	# for increments in increment_options:
	# 	r = ttk.Radiobutton(
	# 		tab1,
	# 		text=increments[0],
	# 		value=increments[1],
	# 				style='TRadiobutton',
	# 		variable=increment
	# 	)
	# 	r.grid(row = i, column = 0, sticky='w', padx=5, pady=5)
	# 	i+=1

	# #movement functions
	# up = tk.Button(tab1, text='↑', width=2, command=lambda : move_z(increment.get()))
	# up.grid(row=4, column=7, padx=20, pady=5)
	# down = tk.Button(tab1, text='↓', width=2, command=lambda : move_z(-increment.get()))
	# down.grid(row=6, column=7, padx=20, pady=5)
	
	# z_label = ttk.Label(tab1, text="z-axis", style='TLabel')
	# z_label.grid(row = 7, column = 7, padx=5, pady=5)
	# left = tk.Button(tab1, text='←', width=2, command=lambda : move_x(-increment.get()))
	# left.grid(row=5, column=3, padx=5, pady=5)
	# right = tk.Button(tab1, text='→', width=2, command=lambda : move_x(increment.get()))
	# right.grid(row=5, column=5, padx=5, pady=5)
	# y_label = ttk.Label(tab1, text="x-axis", style='TLabel')
	# y_label.grid(row = 5, column = 2, padx=5, pady=5)
	# forward = tk.Button(tab1, text='↑', width=2, command=lambda : move_y(-increment.get()))
	# forward.grid(row=4, column=4, padx=5, pady=5)
	# back = tk.Button(tab1, text='↓', width=2, command=lambda : move_y(increment.get()))
	# back.grid(row=6, column=4, padx=5, pady=5)
	# x_label = ttk.Label(tab1, text="y-axis", style='TLabel')
	# x_label.grid(row = 7, column = 4, padx=5, pady=5)
	# set_center = tk.Button(tab1, text='SET CENTER', width=20, command=lambda : set_center_position()) ; set_center.grid(row=8, column=1, padx=5, pady=5)
	# move_to_center = tk.Button(tab1, text='MOVE TO CENTER', width=20, command=lambda : move_head(x=cen_x, y=cen_y)) ; move_to_center.grid(row=9, column=1, padx=5, pady=5)
	# set_target_z = tk.Button(tab1, text='SET SURFACE Z', width=20, command=lambda : set_target_z_position()) ; set_target_z.grid(row=10, column=1, padx=5, pady=5)
	# move_to_target_z = tk.Button(tab1, text='MOVE TO SURFACE Z', width=20, command=lambda : move_head(z=tar_z)) ; move_to_target_z.grid(row=11, column=1, padx=5, pady=5)
	# points_label = ttk.Label(tab1, text="Using Center point", style='TLabel')
	# points_label.grid(row = 9, column = 8, padx=5, pady=5)
	# set_point1 = tk.Button(tab1, text='SET Point', width=20, command=lambda : set_a_point(points_label))
	# set_point = tk.Button(tab1, text='Single Point ON', width=20, relief='sunken') ; set_point.grid(row=8, column=8, padx=5, pady=5)
	# set_point.config(command=lambda : set_point_mode(set_point,set_point1,points_label))
	# ttk.Label(tab2,text="Set Current/Voltage Mode:",style='TLabel').grid(row=10,column=8, padx=40, pady=5)
	# set_mode = tk.Button(tab2, text='Current Mode', width=20, relief='sunken') ; set_mode.grid(row=11, column=8, padx=5, pady=5)
	

	# #Operational Parameters
	# distance_label = ttk.Label(tab2, text="Distance of WE from CE (mm):", style='TLabel')
	# distance_label.grid(row = 0, column = 0, sticky='w', padx=5, pady=5)
	# duration_label = ttk.Label(tab2, text="Electrodeposition time (sec):", style='TLabel')
	# duration_label.grid(row = 1, column = 0, sticky='w', padx=5, pady=5)
	# current_label = ttk.Label(tab2, text="Set a Current (mA):", style='TLabel')
	# current_label.grid(row = 2, column = 0, sticky='w', padx=5, pady=5)
	# voltage_label = ttk.Label(tab2, text="Set a Voltage (V):", style='TLabel')
	# voltage_label.grid(row = 3, column = 0, sticky='w', padx=5, pady=5)
	# input_distance = tk.Text(tab2, height=1, width=5) ; input_distance.grid(row=0, column=1, sticky='w', padx=5, pady=5)
	# input_duration = tk.Text(tab2, height=1, width=5) ; input_duration.grid(row=1, column=1, sticky='w', padx=5, pady=5)
	# input_current = tk.Text(tab2, height=1, width=5) ; input_current.grid(row=2, column=1, sticky='w', padx=5, pady=5)
	# input_voltage = tk.Text(tab2, height=1, width=5) ; input_voltage.grid(row=3, column=1, sticky='w', padx=5, pady=5)
	# set_distance = tk.Button(tab2, text='SET DISTANCE', width=20, command=lambda : set_distance_position(input_distance)) ; set_distance.grid(row=0, column=2, padx=5, pady=5)
	# set_duration = tk.Button(tab2, text='SET DURATION', width=20, command=lambda : set_duration_time(input_duration)) ; set_duration.grid(row=1, column=2, padx=5, pady=5)
	# set_current = tk.Button(tab2, text='SET CURRENT', width=20, command=lambda : set_current_target(input_current)) ; set_current.grid(row=2, column=2, padx=5, pady=5)
	# set_voltage = tk.Button(tab2, text='SET VOLTAGE', width=20, command=lambda : set_voltage_target(input_voltage)) ; set_voltage.grid(row=3, column=2, padx=5, pady=5)
	
	
	# set_voltage.config(state="disabled")
	# input_voltage.config(state="disabled")
	# ttk.Label(tab2,text="Set Current/Voltage Mode:",style='TLabel').grid(row=10,column=8, padx=40, pady=5)
	# set_mode = tk.Button(tab2, text='Current Mode', width=20, relief='sunken') ; set_mode.grid(row=11, column=8, padx=5, pady=5)

	
    # #setting commmand for current mode/voltage mode button
	# set_mode.config(command=lambda : set_mode_electroplating(set_mode,input_current,set_current,input_voltage,set_voltage))
		
	

	#electroplating functions
	# start = tk.Button(tab2, text='START ELECTROPLATING', width=20, command=lambda : do_task(cur_label,vol_label,tar_vol_label,time_remaining_label)) ; start.grid(row=4, column=2, sticky='w', padx=5, pady=50)

	#data downloading
	# download = tk.Button(tab4, text='DOWNLOAD DATA', width=20, command=lambda : download_data()) ; download.grid(row=0, column=0, sticky='w', padx=5, pady=5)

	# ani = animation.FuncAnimation(fig, animate, interval=1000)
	# plt.show()
	m.mainloop()

def build_controllerUI():
	global control_frm,btn_frm
	root = m
	control_frm = tk.Frame(root,bg="#646f7a",borderwidth=100,border=5,padx=20,)
	control_frm.grid(column=0,row=0)
	
	btn_frm = ttk.Frame(root)
	btn_frm.grid(column=1,row=0)
	

	# homing function
	homing = tk.Button(control_frm, text='Home',width=5, command=lambda : head_home()) ; homing.grid(row = 7, column = 1)


	# setting increment
	increment = tk.DoubleVar(None, 1.0)
	increment_options = (('0.1', 0.1), ('1', 1.0), ('10', 10.0), ('100', 100.0))

	increment_label = ttk.Label(control_frm, text="Select Printer Step Size (mm):", style='TLabel')
	increment_label.grid(row = 3, column = 0, padx=5, pady=5)
	i=4
	for increments in increment_options:
		r = ttk.Radiobutton(
			control_frm,
			text=increments[0],
			value=increments[1],
					style='TRadiobutton',
			variable=increment
		)
		r.grid(row = i, column = 0, sticky='w', padx=5, pady=5)
		i+=1

	#movement functions
	up = tk.Button(control_frm, text='➚', width=2, command=lambda : move_z(increment.get()))
	up.grid(row=4, column=7, padx=20, pady=5)
	down = tk.Button(control_frm, text='➘', width=2, command=lambda : move_z(-increment.get()))
	down.grid(row=6, column=7, padx=20, pady=5)
	
	z_label = ttk.Label(control_frm, text="z-axis", style='TLabel')
	z_label.grid(row = 7, column = 7, padx=5, pady=5)
	left = tk.Button(control_frm, text='⬅', width=2, command=lambda : move_x(-increment.get()))
	left.grid(row=5, column=3, padx=5, pady=5)
	right = tk.Button(control_frm, text='➡', width=2, command=lambda : move_x(increment.get()))
	right.grid(row=5, column=5, padx=5, pady=5)
	y_label = ttk.Label(control_frm, text="x-axis", style='TLabel')
	y_label.grid(row = 5, column = 2, padx=5, pady=5)
	forward = tk.Button(control_frm, text='⬆', width=2, command=lambda : move_y(-increment.get()))
	forward.grid(row=4, column=4, padx=5, pady=5)
	back = tk.Button(control_frm, text='⬇', width=2, command=lambda : move_y(increment.get()))
	back.grid(row=6, column=4, padx=5, pady=5)
	x_label = ttk.Label(control_frm, text="y-axis", style='TLabel')
	x_label.grid(row = 7, column = 4, padx=5, pady=5)
	set_center = tk.Button(control_frm, text='Set Center', width=20, command=lambda : set_center_position()) #; set_center.grid(row=8, column=1, padx=5, pady=5)
	move_to_center = tk.Button(control_frm, text='⦿', width=2, command=lambda : move_head_center()) ; #move_to_center.grid(row=5, column=4, padx=5, pady=5)
	set_target_z = tk.Button(btn_frm, text='Set Baseline Height', width=20, command=lambda : set_target_z_position()) ; set_target_z.grid(row=10, column=1, padx=5, pady=5)
	move_to_target_z = tk.Button(control_frm, text='Move To Surface Z', width=20, command=lambda : move_head(z=tar_z)) #; move_to_target_z.grid(row=11, column=1, padx=5, pady=5)
	points_label = ttk.Label(btn_frm, text="Using Center point", style='TLabel')
	points_label.grid(row = 9, column = 8, padx=5, pady=5)
	
	# set_point = tk.Button(btn_frm, text='Single Point ON', width=20, relief='sunken') ; #set_point.grid(row=8, column=8, padx=5, pady=5)
	# set_point.config(command=lambda : set_point_mode(set_point,set_point1,points_label))
	set_params = tk.Button(btn_frm,text="Set Electroplating Variables",width=20,command=lambda:open_param_menu(),bg="#3E9B8B",fg="white") ; set_params.grid(row=12,column=8, padx=5, pady=50)
	undo_point = tk.Button(btn_frm,text="Undo Geometric Area") ; undo_point.grid(row=11,column=8)
	undo_point.config(command=lambda:undo_set_point(points_label,undo_point))
	set_point1 = tk.Button(btn_frm, text='Set Geometric Area', width=20, command=lambda : set_a_point(points_label,undo_point))
	set_point1.grid(row=10, column=8, padx=5, pady=5)

	# points_disp = tk.Canvas(btn_frm,height=100,width=100,bg="#646f7a").grid(row=0,column=8)

	

def open_param_menu():
	control_frm.grid_forget()
	btn_frm.grid_forget()
	build_param_menu()

def open_controller():
	param_frm.grid_forget()
	build_controllerUI()

def build_param_menu():
	global input_distance,input_duration,input_current,input_voltage,param_frm
	# param_root = tk.Tk()
	#Operational Parameters
	param_frm = ttk.Frame(m,style='TFrame')
	param_frm.grid()
	distance_label = ttk.Label(param_frm, text="Distance of WE from CE (mm):", style='TLabel')
	distance_label.grid(row = 0, column = 0, sticky='w', padx=5, pady=5)
	duration_label = ttk.Label(param_frm, text="Electrodeposition time (sec):", style='TLabel')
	duration_label.grid(row = 1, column = 0, sticky='w', padx=5, pady=5)
	current_label = ttk.Label(param_frm, text="Set a Current (mA):", style='TLabel')
	current_label.grid(row = 2, column = 0, sticky='w', padx=5, pady=5)
	voltage_label = ttk.Label(param_frm, text="Set a Voltage (V):", style='TLabel')
	voltage_label.grid(row = 3, column = 0, sticky='w', padx=5, pady=5)
	input_distance = tk.Text(param_frm, height=1, width=5,wrap='none') ; input_distance.grid(row=0, column=1, sticky='w', padx=5, pady=5)
	input_duration = tk.Text(param_frm, height=1, width=5,wrap='none') ; input_duration.grid(row=1, column=1, sticky='w', padx=5, pady=5)
	input_current = tk.Text(param_frm, height=1, width=5,wrap='none') ; input_current.grid(row=2, column=1, sticky='w', padx=5, pady=5)
	input_voltage = tk.Text(param_frm, height=1, width=5,wrap='none') ; input_voltage.grid(row=3, column=1, sticky='w', padx=5, pady=5)
	set_distance = tk.Button(param_frm, text='SET DISTANCE', width=20, command=lambda : set_distance_position(input_distance)) ; #set_distance.grid(row=0, column=2, padx=5, pady=5)
	set_duration = tk.Button(param_frm, text='SET DURATION', width=20, command=lambda : set_duration_time(input_duration)) ; #set_duration.grid(row=1, column=2, padx=5, pady=5)
	set_current = tk.Button(param_frm, text='SET CURRENT', width=20, command=lambda : set_current_target(input_current)) ; #set_current.grid(row=2, column=2, padx=5, pady=5)
	set_voltage = tk.Button(param_frm, text='SET VOLTAGE', width=20, command=lambda : set_voltage_target(input_voltage)) ; #set_voltage.grid(row=3, column=2, padx=5, pady=5)
	
	
	
	set_voltage.config(state="disabled")
	input_voltage.config(state="disabled")
	ttk.Label(param_frm,text="Set Current/Voltage Mode:",style='TLabel').grid(row=0,column=8, padx=40, pady=5)
	set_mode = tk.Button(param_frm, text='Current Mode', width=20, relief='sunken') ; set_mode.grid(row=1, column=8, padx=15, pady=5)

	
    #setting commmand for current mode/voltage mode button
	set_mode.config(command=lambda : set_mode_electroplating(set_mode,input_current,set_current,input_voltage,set_voltage))
	
	start_btn = tk.Button(param_frm,text="▶ START ELECTOPLATING!",width=20,command=lambda : do_task())
	start_btn.grid(row=11,column=8)

	returnbtn = tk.Button(param_frm,text="Return to\nController",width=20,command=lambda: open_controller()); returnbtn.grid(column=0,row=11,pady=15)


def open_experiment_data():
	global cur_label,vol_label,tar_vol_label,time_remaining_label, top,frm
	top = tk.Toplevel(m)
	frm = ttk.Frame(top,style="TFrame")
	
	cur_label = tk.Label(frm)
	vol_label = tk.Label(frm)
	tar_vol_label = tk.Label(frm)
	time_remaining_label = tk.Label(frm)
	#value display	
	# frm.lift(param_frm)
	frm.grid()
	
	cur_label.config(text=cur)
	cur_label.grid(row=0, column=0, sticky='w', padx=5, pady=5)
	
	vol_label.config(text=vol)
	vol_label.grid(row=1, column=0, sticky='w', padx=5, pady=5)
	
	tar_vol_label.config(text=tar_vol)
	tar_vol_label.grid(row=2, column=0, sticky='w', padx=5, pady=5)
	
	time_remaining_label.config(text="time left: no reading yet")
	time_remaining_label.grid(row=3, column=0, sticky='w', padx=5, pady=5)

def do_task():
	if set_distance_position(input_distance) !=True:
		return
	if set_duration_time(input_duration) != True:
		return
	
	if get_current_mode():
	    if set_current_target(input_current) != True:
		    return			
	else:
		if set_voltage_target(input_voltage) != True:
			return
	open_experiment_data()
	threading.Thread(target=lambda: start_electroplating(cur_label,vol_label,tar_vol_label,time_remaining_label), args=()).start()
	
if __name__ == "__main__":
	setup()
	assignbasic_vals()
	# build_controllerUI()
	buildUI()