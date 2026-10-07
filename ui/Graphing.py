import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter, MaxNLocator
import numpy as np
import constvals 
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, 
NavigationToolbar2Tk)
import ElectroplatingUI
import math
import tkinter as tk
import threading

# Creates and returns new array without empty strings
#
# arr = List(Any)
def clean_array(arr):
    tmp_arr = []
    for i in arr:
        if i != "":
            tmp_arr.append(i)
    return tmp_arr

def get_center_arr(arr):
    return arr[math.ceil(len(arr)/2)]

def get_midpoint(a,b):
    return (a+b)/2

def set_text_center(txt):
    txt.set_bbox(dict(facecolor="#4ac534", alpha=0))
    bbox = txt.get_bbox_patch()
    center_x = bbox.get_width()/2
    center_y = bbox.get_height()/2

    # center_x = 0
    # center_y = 0

    print(f"Center X: {center_x}")
    print(f"Center Y: {center_y}")
    # print(f"Text position: {txt.get_position}")
    txt.set_position(((txt.get_position()[0]-center_x),(txt.get_position()[1]-center_y)))

def create_graph(dictionary):
    # print(f"Dictionary:\n{dictionary}")

    voltage_color = "red"
    current_color = "blue"

    point_symbol = "-o"

    fig,ax = plt.subplots()
    fig.suptitle("Plot of Voltage (V) and Current (mA) vs. Time (s)")
    
    volt_arr = dictionary[constvals.DATA_ACTUAL_VOLTAGE]
    curr_arr = dictionary[constvals.DATA_CURRENT]

    volt_arr = clean_array(volt_arr)
    curr_arr = clean_array(curr_arr)

    ax.set_xlabel("Time (Seconds)")
    x = np.array(clean_array(dictionary[constvals.DATA_TOTAL_TIME]))

    # print(f"Total Time Array: {str(x)}")
    # print(f"Voltage: {volt_arr}")
    # print(f"Current: {curr_arr}")

    func, = ax.plot(x,volt_arr,point_symbol,color=voltage_color)
    func.set_label("Voltage (V)")
    ax.set_ylabel("Voltage (V)",color=voltage_color,labelpad=20)
    ax.tick_params(axis="y",colors=voltage_color)

    ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

    ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

    axe = ax.twinx()
    func, = axe.plot(x,curr_arr,point_symbol,color=current_color)
    func.set_label("Current (mA)")
    axe.set_ylabel("Current (mA)",color=current_color,labelpad=20)
    axe.tick_params(axis="y",colors=current_color)

    axe.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axe.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

    fig_size = fig.get_size_inches()*fig.dpi
    font_size = fig_size[0]/10
    font_color = "#5590b0cd"
    if len(constvals.points_coordinates) == 0:
        print("Missing Geometric Points")
        return
    font_size = font_size/len(constvals.points_coordinates)
    if len(constvals.points_coordinates)!=1:
        colored = False
        x_start = 0

        for point in constvals.points_coordinates:
            print(f"Point: {point}")
            endpoint = x_start + constvals.duration

            txt = ax.text(get_midpoint(x_start,endpoint),get_center_arr(volt_arr),f"X: {point[0]}\nY: {point[1]}",size=font_size,color=font_color)
            set_text_center(txt)

            if colored:
                colored = False
                x_start = endpoint
                continue
            
            plt.axvspan(x_start,endpoint,color="#7dea827c")

            colored = True
            x_start = endpoint
    else:
        print(f"Point: {constvals.points_coordinates[0]}")
        txt = ax.text(get_center_arr(x),get_center_arr(volt_arr),f"X: {constvals.points_coordinates[0][0]}\nY: {constvals.points_coordinates[0][1]}",size=font_size,color=font_color)
        # print(f"Bounding box: {txt.get_bbox_patch()}")
        set_text_center(txt)
        
    fig.legend()
    return fig

# Embeds a graph of the experiment in a tkinter frame. 
# The graph compares the experimental Current (mA) and voltage (V) vs. Time (s) 
#
# dictionary = dict(str,list)
# frm = tkinter.ttk.Frame()
def embed_graph(dictionary,frm):
    fig = create_graph(dictionary)

    canvas = FigureCanvasTkAgg(fig, master = frm)  
    canvas.draw()

    toolbar = NavigationToolbar2Tk(canvas,frm)
    toolbar.update()

    canvas.get_tk_widget().pack()

# Creates a new window, showcasing a graph of the experiment. 
# The graph compares the experimental Current (mA) and voltage (V) vs. Time (s) 
#
# dictionary = dict(str,list)
def DispGraph(dictionary):
    create_graph(dictionary) 
    plt.show()
   
def test_embed(dictionary):
    root = tk.Tk()
    frame = tk.Frame(root)
    frame.grid()
    embed_graph(dictionary,frame)

    root.mainloop()

def do_task(dictionary):
    threading.Thread(target=lambda:test_embed(dictionary)).start()

if __name__=="__main__":
    #initializing constvals variables
    constvals.get_start()

    # Testing Code
    lst = []
    lst2 = []
    lst3 = []
    lst4 = []

    constvals.points_coordinates.append((5,4))
    constvals.points_coordinates.append((134,146))
    constvals.points_coordinates.append((12,34))
    constvals.points_coordinates.append((234,254))
    
    factor = 1

    for point in constvals.points_coordinates:
        print(f"Start: {(factor-1)*100}\nEnd: {100*factor}")
        for i in range((factor-1)*100,100*factor):
            # lst.append(np.random.randint(0,20))
            lst.append((i**2)*-1)
            lst2.append((i*2)-1)
            lst3.append(i*3 - 1)
            lst4.append(i*0.2*0.05)
        factor += 1
    dictionary = {
        constvals.DATA_CURRENT:lst,
        constvals.DATA_TARGET_VOLTAGE:lst2,
        constvals.DATA_ACTUAL_VOLTAGE:lst3,
        constvals.DATA_TOTAL_TIME:lst4
    }

    # print(dictionary)
    # print(f"Voltage: {lst2}")
    # print(f"Current: {lst}")

    

    # print(lst4)
    do_task(dictionary)
    # test_embed(dictionary)
    # DispGraph(dictionary)
    
        