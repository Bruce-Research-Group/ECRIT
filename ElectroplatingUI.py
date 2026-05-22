import tkinter as tk
from tkinter import ttk
from SendCommandSerial import *

def buildUI():
	setup()
	assignbasic_vals()
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
	
	global cur,vol,tar_vol,vol_list,time_list
	# values
	cur = "Current: no reading yet"
	vol = "Actual Voltage: no reading yet"
	tar_vol = "Target Voltage: no reading yet"
	vol_list = []
	time_list = []
	
	build_controllerUI()
	
	m.mainloop()

def build_controllerUI():
	global control_frm,btn_frm
	root = m
	root.wm_minsize(width=650,height=550)
	root.grid_columnconfigure(list(range(0,1)),weight=1)
	root.grid_rowconfigure(list(range(0,1)),weight=1)

	control_frm = tk.Frame(root,bg="#2E3440",borderwidth=100,border=5,padx=20,pady=20)
	control_frm.grid(column=0,row=0)
	control_frm.grid_columnconfigure(list(range(0,12)),weight=2)
	control_frm.grid_rowconfigure(list(range(0,12)),weight=2)
	
	btn_frm = tk.Frame(root,bg="#646f7a",borderwidth=100,border=5,padx=20,pady=20)
	btn_frm.grid(column=0,row=1,ipadx=150)
	btn_frm.grid_columnconfigure(list(range(0,15)),weight=1)
	btn_frm.grid_columnconfigure(list(range(0,15)),weight=1)
	

	# homing function
	homing = tk.Button(control_frm, text='Home',width=5, command=lambda : head_home()) ; homing.grid(row = 3, column = 0,padx=(0,100))


	# setting increment
	increment = tk.DoubleVar(None, 1.0)
	increment_options = (('0.1', 0.1), ('1', 1.0), ('10', 10.0), ('100', 100.0))

	increment_label = ttk.Label(control_frm, text="Select Printer Step Size (mm):", style='TLabel')
	increment_label.grid(row = 3, column = 1, padx=5, pady=5)
	i=4
	for increments in increment_options:
		r = ttk.Radiobutton(
			control_frm,
			text=increments[0],
			value=increments[1],
					style='TRadiobutton',
			variable=increment
		)
		r.grid(row = i, column = 1, sticky='w', padx=5, pady=5)
		i+=1

	#movement functions
	up = tk.Button(control_frm, text='➚', width=2, command=lambda : move_z(increment.get()))
	up.grid(row=4, column=7, padx=20, pady=5)
	down = tk.Button(control_frm, text='➘', width=2, command=lambda : move_z(-increment.get()))
	down.grid(row=6, column=7, padx=20, pady=5)

	# up.config(text="⇬")
	# down.config(text="")

	# up_arrow = tk.PhotoImage(file="Icons/UpArrow.png")
	# down_arrow = tk.PhotoImage(file="Icons/DownArrow.png")
	# left_arrow = tk.PhotoImage(file="Icons/LeftArrow.png")
	# right_arrow = tk.PhotoImage(file="Icons/RightArrow.png")

	# img_shrinkfactor = 20
	# up_arrow = up_arrow.subsample(img_shrinkfactor,img_shrinkfactor)
	# down_arrow = down_arrow.subsample(img_shrinkfactor,img_shrinkfactor)
	# left_arrow = left_arrow.subsample(img_shrinkfactor,img_shrinkfactor)
	# right_arrow = right_arrow.subsample(img_shrinkfactor,img_shrinkfactor)

	
	z_label = ttk.Label(control_frm, text="z-axis", style='TLabel')
	z_label.grid(row = 7, column = 7, padx=5, pady=5)
	left = tk.Button(control_frm, text='←', width=2, command=lambda : move_x(-increment.get()))
	left.grid(row=5, column=3, padx=5, pady=5)
	# left.config(image=left_arrow)
	right = tk.Button(control_frm, text='→', width=2, command=lambda : move_x(increment.get()))
	right.grid(row=5, column=5, padx=5, pady=5)
	# right.config(image=right_arrow)
	y_label = ttk.Label(control_frm, text="x-axis", style='TLabel')
	y_label.grid(row = 5, column = 2, padx=5, pady=5)
	forward = tk.Button(control_frm, text='↑', width=2, command=lambda : move_y(-increment.get()))
	forward.grid(row=4, column=4, padx=5, pady=5)
	# forward.config(image=up_arrow)
	back = tk.Button(control_frm, text='↓', width=2, command=lambda : move_y(increment.get()))
	back.grid(row=6, column=4, padx=5, pady=5)
	# back.config(image=down_arrow)
	x_label = ttk.Label(control_frm, text="y-axis", style='TLabel')
	x_label.grid(row = 7, column = 4, padx=5, pady=5)
	set_center = tk.Button(control_frm, text='Set Center', width=20, command=lambda : set_center_position()) #; set_center.grid(row=8, column=1, padx=5, pady=5)
	move_to_center = tk.Button(control_frm, text='⦿', width=2, command=lambda : move_head_center()) ; #move_to_center.grid(row=5, column=4, padx=5, pady=5)
	set_target_z = tk.Button(btn_frm, text='Set Baseline Height', width=20, command=lambda : set_target_z_position()) ; set_target_z.grid(row=10, column=1, padx=5, pady=5)
	move_to_target_z = tk.Button(control_frm, text='Move To Surface Z', width=20, command=lambda : move_head(z=tar_z)) #; move_to_target_z.grid(row=11, column=1, padx=5, pady=5)
	points_label = tk.Label(btn_frm, text="0",fg="white",font="Helvetica",bg="#646f7a")
	points_label.grid(row = 9, column = 8, padx=5, pady=15)
	
	# set_point = tk.Button(btn_frm, text='Single Point ON', width=20, relief='sunken') ; #set_point.grid(row=8, column=8, padx=5, pady=5)
	# set_point.config(command=lambda : set_point_mode(set_point,set_point1,points_label))
	set_params = tk.Button(btn_frm,text="Next",width=20,command=lambda:open_param_menu(),bg="#3E9B8B",fg="white",font="Helvetica 10 bold") ; set_params.grid(row=12,column=9, pady=(50,0),ipadx=10,padx=(75,0))
	undo_point = tk.Button(btn_frm,text="↩ Undo Geometric Area") ; undo_point.grid(row=11,column=8)
	undo_point.config(command=lambda:undo_set_point(points_label,undo_point),state="disabled")
	set_point1 = tk.Button(btn_frm, text='Set Geometric Area', width=20, command=lambda : set_a_point(points_label,undo_point))
	set_point1.grid(row=10, column=8, padx=5, pady=5)
	print(m.winfo_geometry())
	
	# get_win_size = tk.Button(btn_frm,text="get win dimensions",command=lambda:get_minsize(m)) ; get_win_size.grid(row=10, column=1, padx=5, pady=5)
	# points_disp = tk.Canvas(btn_frm,height=100,width=100,bg="#646f7a").grid(row=0,column=8)

def get_minsize(window):
	print(window.winfogeometry())

def open_param_menu():
	control_frm.grid_forget()
	btn_frm.grid_forget()
	build_param_menu()
	m.wm_minsize(width=600,height=200)

def open_controller():
	param_frm.grid_forget()
	build_controllerUI()
	m.wm_minsize(width=650,height=550)


def build_param_menu():
	global input_distance,input_duration,input_current,input_voltage,param_frm
	# param_root = tk.Tk()
	#Operational Parameters
	param_frm = ttk.Frame(m,style='TFrame')
	param_frm.grid()
	distance_label = ttk.Label(param_frm, text="Distance Between WE and CE (mm):", style='TLabel')
	distance_label.grid(row = 0, column = 0, sticky='w', padx=5, pady=5)
	duration_label = ttk.Label(param_frm, text="Electrodeposition Time (sec):", style='TLabel')
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
	
	voltage_label.config(state="disabled")
	
	
	set_voltage.config(state="disabled")
	input_voltage.config(state="disabled")

	ttk.Label(param_frm,text="Set Mode:",style='TLabel').grid(row=0,columnspan=2,column=8, padx=40, pady=5)
	set_mode = tk.Button(param_frm, text='Current Mode', width=20, relief='sunken') ; #set_mode.grid(row=1, column=8, padx=15, pady=5)

	set_volt = tk.Button(param_frm,text='Voltage Mode', width=10) ; set_volt.grid(row=1, column=8, padx=(15,5), pady=5, ipadx=2)
	set_curr = tk.Button(param_frm,text='Current Mode', width=10) ; set_curr.grid(row=1, column=9, padx=5, pady=5, ipadx=2)

	set_volt.config(command=lambda:set_voltage_mode(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label,set_volt,set_curr))
	set_curr.config(command=lambda:set_current_mode(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label,set_volt,set_curr))
	set_curr.config(bg="#b1c6eb")
	
    #setting commmand for current mode/voltage mode button
	set_mode.config(command=lambda : set_mode_electroplating(set_mode,input_current,set_current,input_voltage,set_voltage,current_label,voltage_label))
	
	start_btn = tk.Button(param_frm,text="▶ START ELECTOPLATING!",width=20,command=lambda : do_task(),bg="#3E9B8B",fg="white",font="Helvetica 10 bold")
	start_btn.grid(row=11,column=8,ipadx=5,columnspan=3,pady=(15,15))

	returnbtn = tk.Button(param_frm,text="Go\nBack",width=10,command=lambda: open_controller(),bg="#7A3A30",fg="white"); returnbtn.grid(column=0,row=11,pady=(15,10),sticky="w",padx=(10,0))


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
	
	time_remaining_label.config(text="Time left: no reading yet")
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
	threading.Thread(target=lambda: start_electroplating(cur_label,vol_label,tar_vol_label,time_remaining_label,vol_list,time_list), args=()).start()
	
if __name__ == "__main__":
	setup()
	assignbasic_vals()
	# build_controllerUI()
	buildUI()