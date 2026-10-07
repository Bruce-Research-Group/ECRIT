import time
import queue
import threading

class ThreadHandler:
    instance = None
    print("Initializing thread handler...")  
    main_thread = queue.Queue()
                

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
            # cls.main_thread = queue.Queue()
        return cls.instance
    
    def from_dummy_thread(cls,func_to_call_from_main_thread):
        cls.main_thread.put(func_to_call_from_main_thread)

    def from_main_thread_blocking(cls):
        callback = cls.main_thread.get() #blocks until an item is available
        callback()

    def from_main_thread_nonblocking(cls):
        while True:
            try:
                callback = cls.main_thread.get(False) #doesn't block
            except queue.Empty: #raised when queue is empty
                break
            callback()

    def run_main_thread():
        ...


    def AddToMainQueue(cls,func):
        cls.main_thread.put(func)
    
    def AddMultiple(cls,lst):
        for func in lst:
            cls.main_thread.put(func)
    
    def dequeue(cls):
        return cls.main_thread.get()

    def __str__(cls):
        string = "{"
        tmp_queue = queue.Queue()
        queue_size = int(cls.main_thread.qsize())
        for i in range(1,queue_size+1):
            item = cls.main_thread.get()
            tmp_queue.put(item)
            string += str(i)+":"+str(item)
            if i != queue_size:
                string += ", "
        string+="}"
        cls.main_thread = tmp_queue
        return string


def test_func(a,b):
    print("adding...")
    return a+b
def test2_func(a,b):
    print("multiplying...")
    return a*b

if __name__ == "__main__":
    print("making handler one")
    handler = ThreadHandler()
    print("making handler two")
    handler2 = ThreadHandler()
    print(handler is handler2)
    print(handler)
    handler.AddToMainQueue(lambda:test_func(4,6))
    handler2.AddToMainQueue(lambda:test2_func(2,7))

    print(handler)
    print(handler)
    handler.from_main_thread_nonblocking()
    # print(handler.dequeue())
    print(handler2)


