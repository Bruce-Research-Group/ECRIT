from tkinter import *
from tkinter import ttk
from tkinter import messagebox
import time
import ElectroplatingUI

def tooltip(txt,error=True,autoclose=False,close_time=1):
    top = Toplevel()

    #checks whether tooltip is intended to inform user of error or deliver advice
    if error == True:
        # msgbox = messagebox.showerror("Error!",txt)
        top.title("Error!")
    else:
        # msgbox = messagebox.showinfo("Quick Tip!",txt)
        top.title("Quick Tip!")
    
    # top.title('Welcome')
    Label(top,bitmap="error",padx=20,pady=20).grid(column=1,row=0)
    Message(top, text=txt, padx=50, pady=20,width=100,takefocus=True).grid(column=2,row=0,sticky="nsew")
    top.grid_columnconfigure(2, weight=50)
    # top.grid_rowconfigure((0,1), weight=1, uniform=1)
    print("created tooltip")
    
    if autoclose:
        # time.sleep(10)
        top.after(close_time*1000, top.destroy)

def Calculate_ScreenCenter(root):
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()

    # x = (width/2)+root.

def startmainUI():
    ElectroplatingUI.buildUI()
        
        
#Code to test this file specifically
if __name__ =="__main__":
    root = Tk()
    Button(root, text="Click to register", command=lambda: tooltip("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",autoclose=True)).pack()
    root.mainloop()
    # tooltip("Here's a cool Tip!",error=False)