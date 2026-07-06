import matplotlib.pyplot as plt
import numpy as np
import constvals 

# dictionary = dict(str,list)
# val_name = str #String to select list from dictionary
def DispGraph(dictionary):
    dictionary[constvals.DATA_IND_TIME].pop(0)
    dictionary[constvals.DATA_CURRENT].pop(0)
    dictionary[constvals.DATA_ACTUAL_VOLTAGE].pop(0)
    
    voltage_color = "red"
    current_color = "blue"

    point_symbol = "-o"

    # Labels graph title
    fig,ax = plt.subplots()
    fig.suptitle("Plot of Voltage (V) and Current (mA) vs. Time (s)")

    volt_arr = dictionary[constvals.DATA_ACTUAL_VOLTAGE]
    curr_arr = dictionary[constvals.DATA_CURRENT]

    ax.set_xlabel("Time (Seconds)")
    x = np.array(dictionary[constvals.DATA_IND_TIME])

    func, = ax.plot(x,volt_arr,point_symbol,color=voltage_color)
    func.set_label("Voltage (V)")
    ax.set_ylabel("Voltage (V)",color=voltage_color,labelpad=20)
    ax.tick_params(axis="y",colors=voltage_color)

    axe = ax.twinx()
    func, = axe.plot(x,curr_arr,point_symbol,color=current_color)
    func.set_label("Current (mA)")
    axe.set_ylabel("Current (mA)",color=current_color,labelpad=20)
    axe.tick_params(axis="y",colors=current_color)
    
    fig.legend() 
    plt.show()
    

if __name__=="__main__":
    #initializing constvals variables
    constvals.get_start()

    # Testing Code
    lst = []
    lst2 = []
    lst3 = []
    lst4 = []

    for i in range(0,25):
        # lst.append(np.random.randint(0,20))
        lst.append((i**2)*-1)
        lst2.append((i*2)-1)
        lst3.append(i*3 - 1)
        lst4.append(i*0.2)
    dictionary = {
        constvals.DATA_CURRENT:lst,
        constvals.DATA_TARGET_VOLTAGE:lst2,
        constvals.DATA_ACTUAL_VOLTAGE:lst3,
        constvals.DATA_IND_TIME:lst4
    }
    print(f"Voltage: {lst2}")
    print(f"Current: {lst}")
    DispGraph(dictionary)
    
        