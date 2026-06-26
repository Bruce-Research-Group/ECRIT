import matplotlib.pyplot as plt
import numpy as np
import constvals 

# dictionary = dict(str,list)
# val_name = str #String to select list from dictionary
def DispGraph(dictionary):
    dictionary[constvals.DATA_IND_TIME].pop(0)
    dictionary[constvals.DATA_CURRENT].pop(0)
    dictionary[constvals.DATA_ACTUAL_VOLTAGE].pop(0)
    val_names = [constvals.DATA_CURRENT,constvals.DATA_ACTUAL_VOLTAGE]
    # Labels graph title
    plt.title("Plot of Voltage (V) and Current (mA) vs. Time (s)")
    
    for val_name in val_names:
        # Gets data array from dictionary
        exp_values= dictionary[str(val_name)]

        # Loads data array and plots on the graph
        print(f"DATA_IND_TIME: {constvals.DATA_IND_TIME}")
        print(f"Time list: {dictionary[constvals.DATA_IND_TIME]}")
        x = np.array(range(0,len(dictionary[constvals.DATA_IND_TIME])))
        y= np.array(exp_values) 
        func, = plt.plot(x,y,"o")
        func.set_label(val_name)

        # plots line of best fit onto the graph
        plt.plot(np.unique(x), np.poly1d(np.polyfit(x, y, 1))(np.unique(x)))
    
    plt.legend()

    plt.show()
    
    # print("done")

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
        lst4.append(i)
    dictionary = {
        constvals.DATA_CURRENT:lst,
        constvals.DATA_TARGET_VOLTAGE:lst2,
        constvals.DATA_ACTUAL_VOLTAGE:lst3,
        constvals.DATA_IND_TIME:lst4
    }
    DispGraph(dictionary)
        