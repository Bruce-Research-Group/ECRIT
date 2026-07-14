from tkinter import *
from tkinter import ttk
import json
import serial.tools.list_ports
import UtilUI
import constvals

global port_dict
port_dict = {}
#lists available ports in new window and allows user to select from given ports
def selectport(root):
    # print(str(serial.tools.list_ports.comports())) 
    global frm
    frm = Toplevel(root)
    # frm = ttk.Frame(root, padding=100,height=200,width=500)
    frm.grid()
    ttk.Label(frm, text="Select Arduino Port").grid(column=0, row=0)
    ttk.Label(frm, text="Select Printer Port").grid(column=0, row=1)
    
    comports = serial.tools.list_ports.comports()

    global port_dict
    port_list = []
    portid_list = []
    port_dict = {}
    #populate port_list and port_dict
    for i in comports:
        port_id = i.device
        port_str = i.device
        # print(constvals.discovered_arduino)
        # if constvals.discovered_arduino != None and port_str.__eq__(constvals.discovered_arduino):
        if constvals.discovered_arduino != None and port_str in constvals.arduino_ports:
            port_str += " (Arduino)"
        if constvals.discovered_printer != None and port_str in constvals.printer_ports:
            port_str += " (3D Printer)"
        port_list.append(port_str)
        portid_list.append(port_id)
        port_dict.update({port_str:port_id})

    #Dropdown menu
    global arduino_option,printer_option,options_dict
    with open("options.json","r") as f:
        options = json.load(f)
    options_dict = dict(options)
    arduino_option = StringVar()
    printer_option = StringVar()
    if constvals.discovered_arduino != None:
        arduino_option.set(port_list[portid_list.index(constvals.discovered_arduino)])
    else:
        if options[constvals.OPTIONS_ARDUINO] in portid_list:
            arduino_option.set(port_list[portid_list.index(options["arduino_port"])])
    
    if constvals.discovered_printer != None:
        printer_option.set(port_list[portid_list.index(constvals.discovered_printer)])
    else:
        if options[constvals.OPTIONS_PRINTER] in portid_list:
            printer_option.set(port_list[portid_list.index(options["printer_port"])])
    print(printer_option.get())
    print(arduino_option.get())
    OptionMenu(frm,arduino_option,*port_list).grid(column=2,row=0)
    OptionMenu(frm,printer_option,*port_list).grid(column=2,row=1)
    

    #confirmation button
    conbtn = ttk.Button(frm, text="Confirm", command=lambda: confirmport(frm)).grid(column=1, row=2)
    quitbtn = ttk.Button(frm,text="Cancel",command=frm.destroy).grid(column=1,row=3)
    frm.mainloop()
    print("exited mainloop")

def confirmport(frm):
    global port_dict
    if arduino_option.get() == "" or printer_option.get() == "":
        UtilUI.tooltip("You must select a port for both devices",autoclose=True,close_time=2)
        return

    if port_dict[arduino_option.get()] == port_dict[printer_option.get()]:
        UtilUI.tooltip("Arduino Port and Printer Port can NOT be the same",autoclose=True,close_time=2)
        return
    print(f"Printer option: '{printer_option.get()}'")
    options_dict.update({"arduino_port":port_dict[arduino_option.get()]})
    options_dict.update({"printer_port":port_dict[printer_option.get()]})

    with open("options.json","w") as opt_file:
        json.dump(options_dict,opt_file,ensure_ascii=False, indent=4)
    constvals.update_options()
    print("destroying mainloop...")
    frm.destroy()
    print("mainloop destroyed!")

if __name__ == "__main__":
    constvals.attempt_auto_connect()
    root = Tk()
    Button(root,text="Open Select Port Menu",command=lambda: selectport(root)).pack()
    root.mainloop()

