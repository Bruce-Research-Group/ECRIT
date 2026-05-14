import json
import time
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import SelectPort
import UtilUI


exit = False

with open("options.json","r") as f:
		options = json.load(f)

def startprogram():
    global root
    exit = False
    root = Tk()
    root.geometry("500x500")
    root.title("Electrochemistry Experiment Setup")
    frm = ttk.Frame(root, padding=100,height=200,width=500)
    # frm.grid(padx=50,pady=50)
    frm.place()

    #Start Program Buttons
    startbtn = Button(frm,text="Start",command=lambda: autodetectports(root)).place(x=50,y=20)
    # startbtn.grid(column=0,row=0)
    # startbtn.place(anchor=CENTER)
    # startbtn.place()


    portsbtn = Button(frm,text="Configure\nPorts",command=lambda: SelectPort.selectport(root))
    # portsbtn.grid(column=4,row=4,ipady=10,pady=20,padx=100)
    portsbtn.place(anchor=CENTER,rely=-100)

    quitbtn = Button(frm,text="Quit",command=on_quit)
    # quitbtn.grid(column=0,row=1)
    quitbtn.place(anchor=SE)
    
    root.mainloop()
    exit=True
    print(exit)
    print(exit == True)
    # ttk.Label(frm, text="Select Arduino Port").grid(column=0, row=0)
    # ttk.Label(frm, text="Select Printer Port").grid(column=0, row=1)
    # autodetectports()

    # global root
    # root = Tk()
    # root.title("Update Connected Ports?")
    # frm = ttk.Frame(root)
    # frm.grid()
    # ttk.Label(frm,text="Select a new Port?").grid(column=1,row=0)
    # ttk.Button(frm,text="Yes",command=openselectPort).grid(column=0,row=1)
    # ttk.Button(frm,text="No",command=root.destroy).grid(column=2,row=1)
    # root.mainloop()
def portopenerror(root):
    SelectPort.selectport(root)
    print("showcasing prompt")
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
    return exit
    

def autodetectports(root):
    arduino = False
    printer = False

    arduino_port = options["arduino_port"]
    printer_port = options["printer_port"]
    print(printer_port)
    if arduino_port == "" or printer_port =="":
        UtilUI.tooltip("No Registered Port found. Opening port selection menu...",autoclose=True,close_time=2)
        SelectPort.selectport(root)
    try:
        s = serial.Serial(arduino_port)
        s.close
        arduino = True
    except OSError:
        pass
        # UtilUI.tooltip("Could not open arduino port!")
        
    
    try:
        s = serial.Serial(printer_port)
        s.close
        printer = True
    except OSError:
        pass
        # UtilUI.tooltip("Could not open printer port!")
        

    if not arduino or not printer:
        if not arduino: 
            UtilUI.tooltip("Could not open arduino port!",autoclose=True)
        elif not printer:
            UtilUI.tooltip("Could not open printer port!",autoclose=True)
        else:
            UtilUI.tooltip("Could not open either port!",autoclose=True)
        # SelectPort.selectport(root)
        portopenerror(root)
        # print("ports were not valid")
        # SelectPort.selectport()
        # messagebox.askquestion(title="Try Again?",message="Attempt to open ports with new configuration?",type=YESNO)
    # UtilUI.tooltip("Valid ports found! Starting Program...",autoclose=True)
        

    # ports = serial.tools.list_ports.comports()
    # if ports.__len__() <2:
    #     UtilUI.tooltip("Insufficient Number of Ports!")

    # for p in ports:
    #     print(p.device)

def destroy_startmenuroot():
    on_quit()

if __name__ == "__main__":
    # ser = serial.Serial('COM4')
    # print(ser.name) 
    # print(serial.tools.list_ports.comports().__len__())
    startprogram()
    print("Can quit val: "+str(canquit()))
    on_quit()
    # autodetectports()