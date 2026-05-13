from tkinter import *
from tkinter import ttk
import serial
import serial.tools.list_ports
import SelectPort
import UtilUI

def startprogram():
    global root
    root = Tk()
    root.title("Update Connected Ports?")
    frm = ttk.Frame(root)
    frm.grid()
    ttk.Label(frm,text="Select a new Port?").grid(column=1,row=0)
    ttk.Button(frm,text="Yes",command=openselectPort).grid(column=0,row=1)
    ttk.Button(frm,text="No",command=root.destroy).grid(column=2,row=1)
    root.mainloop()

def autodetectports():
    ports = serial.tools.list_ports.comports()
    if ports.__len__() <2:
        UtilUI.tooltip("Insufficient Number of Ports!")
        
    for p in ports:
        print(p.device)


def openselectPort():
    root.destroy()
    SelectPort.selectport()

if __name__ == "__main__":
    
    # print(serial.tools.list_ports.comports().__len__())
    startprogram()