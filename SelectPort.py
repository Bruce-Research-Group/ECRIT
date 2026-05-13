from tkinter import *
from tkinter import ttk
import json
import serial.tools.list_ports
import UtilUI

#lists available ports in new window and allows user to select from given ports
def selectport():
    print(str(serial.tools.list_ports.comports()))
    global root 
    root = Tk()
    frm = ttk.Frame(root, padding=100,height=200,width=500)
    frm.grid()
    ttk.Label(frm, text="Select Arduino Port").grid(column=0, row=0)
    ttk.Label(frm, text="Select Printer Port").grid(column=0, row=1)
    
    port_list = []
    #populate port_list
    for i in serial.tools.list_ports.comports():
        port_list.append(i.device)

    #Dropdown menu
    global arduino_option,printer_option
    arduino_option = StringVar()
    printer_option = StringVar()
    OptionMenu(frm,arduino_option,*port_list).grid(column=2,row=0)
    OptionMenu(frm,printer_option,*port_list).grid(column=2,row=1)
    

    #confirmation button
    conbtn = ttk.Button(frm, text="Confirm", command=confirmport).grid(column=1, row=2)
    quitbtn = ttk.Button(frm,text="Cancel",command=root.destroy).grid(column=1,row=3)
    root.mainloop()

def confirmport():
    if arduino_option.get() == printer_option.get():
        UtilUI.tooltip("Arduino Port and Printer Port can NOT be the same")
        return
    ports = {
        "arduino_port":arduino_option.get(),
        "printer_port":printer_option.get()
    }
    with open("options.json","w") as opt_file:
        json.dump(ports,opt_file,ensure_ascii=False, indent=4)
    root.destroy()

if __name__ == "__main__":
    selectport()

