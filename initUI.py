import json
import time
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import SelectPort
import UtilUI
import constvals

global exit
exit = False

try:
    with open("options.json","r") as f:
            options = json.load(f)
except:
    with open("options.json","w") as f:
        placeholder = {"arduino_port":"","printer_port":""}
        json.dump(placeholder,f)
    with open("options.json","r") as f:
        options = json.load(f)

def startprogram():
    global root,exit
    if exit:
        pass
    exit = False
    root = Tk()
    root.config(bg="#2E3440")
    root.title("Electrochemistry Experiment Setup")
    root.grid_columnconfigure(0,weight=1)
    root.grid_rowconfigure(0,weight=1)

    frm = Frame(root, bg="#2E3440")
    frm.grid(row=0,column=0,padx=50,pady=50)
    frm.grid_rowconfigure(list(range(0,10)),weight=1)
    frm.grid_columnconfigure(list(range(0,10)),weight=1)

    #Start Program Buttons
    startbtn = Button(frm,text="Start",command=lambda: autodetectports(root),width=20)
    startbtn.grid(column=0,row=0,pady=50,padx=(75,40))

    portsbtn = Button(frm,text="Configure\nPorts",command=lambda: SelectPort.selectport(root))
    portsbtn.grid(column=4,row=4,ipady=10,padx=50)

    quitbtn = Button(frm,text="Quit",command=on_quit,width=15)
    quitbtn.grid(column=0,row=1,padx=(75,40),pady=(20,50))
    
    root.mainloop()
    exit=True
    # print(exit)
    # print(exit == True)
    
def portopenerror(root):
    global exit
    if exit:
        pass
    SelectPort.selectport(root)
    # print("showcasing prompt")
    exit=True
    msg = messagebox.askyesno(title="Try Again?",message="Attempt to start program again?")
    if msg:
        startprogram()
    else:
        exit=True

def on_quit():
    global exit
    if exit == False:
        print("Exiting...")
        root.destroy()
    exit = True

def canquit():
    global exit
    return exit
    

def autodetectports(root):
    arduino = False
    printer = False

    arduino_port = options["arduino_port"]
    printer_port = options["printer_port"]
    print(constvals.printer_port)
    if constvals.arduino_port == "" or constvals.printer_port =="":
        UtilUI.tooltip("No Registered Port found. Opening port selection menu...",autoclose=True,close_time=2)
        SelectPort.selectport(root)
    # try:
    #     s = serial.Serial(arduino_port)
    #     s.close()
    #     arduino = True
    # except OSError:
    #     pass
    #     # UtilUI.tooltip("Could not open arduino port!")
        
    
    # try:
    #     s = serial.Serial(printer_port)
    #     s.close()
    #     printer = True
    # except OSError:
    #     pass
    #     # UtilUI.tooltip("Could not open printer port!")
        

    # if not arduino or not printer:
    #     if not arduino: 
    #         UtilUI.tooltip("Could not open arduino port!",autoclose=True)
    #     elif not printer:
    #         UtilUI.tooltip("Could not open printer port!",autoclose=True)
    #     else:
    #         UtilUI.tooltip("Could not open either port!",autoclose=True)
    #     # SelectPort.selectport(root)
    #     portopenerror(root)
    destroy_startmenuroot()

def destroy_startmenuroot():
    on_quit()

if __name__ == "__main__":
    # ser = serial.Serial('COM4')
    # print(ser.name) 
    # print(serial.tools.list_ports.comports().__len__())
    startprogram()
    # print("Can quit val: "+str(canquit()))
    # on_quit()
    # autodetectports()