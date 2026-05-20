from tkinter import *
from tkinter import ttk
import json
import serial.tools.list_ports
import UtilUI

#lists available ports in new window and allows user to select from given ports
def selectport(root):
    print(str(serial.tools.list_ports.comports())) 
    global frm
    frm = Toplevel(root)
    # frm = ttk.Frame(root, padding=100,height=200,width=500)
    frm.grid()
    ttk.Label(frm, text="Select Arduino Port").grid(column=0, row=0)
    ttk.Label(frm, text="Select Printer Port").grid(column=0, row=1)
    
    port_list = []
    #populate port_list
    for i in serial.tools.list_ports.comports():
        port_list.append(i.device)

    #Dropdown menu
    global arduino_option,printer_option
    with open("options.json","r") as f:
        options = json.load(f)
    arduino_option = StringVar()
    printer_option = StringVar()
    arduino_option.set(options["arduino_port"])
    printer_option.set(options["printer_port"])
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
    if arduino_option.get() == printer_option.get():
        UtilUI.tooltip("Arduino Port and Printer Port can NOT be the same",autoclose=True,close_time=2)
        return
    ports = {
        "arduino_port":arduino_option.get(),
        "printer_port":printer_option.get()
    }
    with open("options.json","w") as opt_file:
        json.dump(ports,opt_file,ensure_ascii=False, indent=4)
    print("destroying mainloop...")
    frm.destroy()
    print("mainloop destroyed!")

if __name__ == "__main__":
    root = Tk()
    Button(root,text="Open Select Port Menu",command=lambda: selectport(root)).pack()
    root.mainloop()

