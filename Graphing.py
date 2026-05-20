import matplotlib.pyplot as plt
import numpy as np

# dictionary = dict(str,list)
# val_name = str #String to select list from dictionary
def DispGraph(dictionary,val_name):
    # Gets data array from dictionary
    exp_values= dictionary[str(val_name)]

    # Labels graph title
    plt.title(str(val_name)+" vs. Time (s)")

    # Loads data array and plots on the graph
    x = np.array(range(0,len(exp_values)))
    y= np.array(exp_values) 
    plt.plot(x,y,"o")

    # plots line of best fit onto the graph
    plt.plot(np.unique(x), np.poly1d(np.polyfit(x, y, 1))(np.unique(x)))
    
    plt.show()
    
    # print("done")

if __name__=="__main__":
    # Testing Code
    lst = []
    for i in range(0,25):
        # lst.append(np.random.randint(0,20))
        lst.append((i**2)*-1)
    dictionary = {
        "owo":lst
    }
    DispGraph(dictionary,"owo")
        