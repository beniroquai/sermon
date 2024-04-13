import threading
import serial
import time
import json
import queue
from collections import deque

class RingBuffer(deque):
    def __init__(self, size_max):
        super().__init__(maxlen=size_max)

    def append(self, datum):
        super().append(datum)
        return self

    def get(self):
        return list(self)
class SimpleSerialComm:
    def __init__(self, port, baudrate=9600):
        self.serial_port = serial.Serial(port, baudrate=baudrate, timeout=0)
        
        self.data_queue = queue.Queue()
        time.sleep(1)
        self.alive = False
        self.read_thread = None
        maxQentries = 100
        self.queueFinalizedQueryIDs = RingBuffer(maxQentries)
        #self.serial_io_lock = threading.Lock()
        # read for 100 lines
        nEmptyLines = 0
        for _ in range(1000):
            mLine = self.serial_port.readline()
            print(mLine)
            if mLine==b"":
                nEmptyLines +=1
                if nEmptyLines > 5:
                    break
            time.sleep(0.02)
            
        
    def start_reading(self):
        """Start reading serial port in a separate thread."""
        if not self.alive:
            self.alive = True
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.start()
            self.worker_thread = threading.Thread(target=self._process_data)
            self.worker_thread.start()
        

    def stop_reading(self):
        """Stop reading loop and close serial port."""
        if self.alive:
            self.alive = False
            self.read_thread.join()
        if self.serial_port.is_open:
            self.serial_port.close()


    def extract_json_objects(self, s):
        """
        Extract JSON objects from a string that starts with '++' and ends with '--',
        and return the remaining string after the last successful JSON extraction.
        
        Parameters:
        - s (str): The input string containing JSON objects.
        
        Returns:
        - List[dict]: A list of dictionaries parsed from the JSON objects in the string.
        - str: The remaining part of the string after the last successful JSON object extraction.
        """
        parts = s.split('++')
        dictionaries = []
        last_position = 0  # Track the position in the original string
        remainder = ""  # Track the remaining string after the last successful JSON extraction
        for part in parts:
            # Attempt to extract the JSON string
            json_str = part.split('--')[0].strip()
            if json_str:
                try:
                    # Update the position tracker to the end of the current part
                    last_position += len(part) + 2  # +2 accounts for the '++' delimiter
                    json_dict = json.loads(json_str)
                    dictionaries.append(json_dict)
                except json.JSONDecodeError as e:
                    try:
                        #trying to repair the string
                        import re
                        match = re.search(r'"qid":(\d+)', json_str)
                        if match:
                            qid = int(match.group(1)) 
                            json_dict = {"qid": qid}
                            dictionaries.append(json.loads(json.dumps(json_dict)))
                    except Exception as e:
                        print(f"Failed to decode JSON: {json_str}. Error: {e}")
                        last_position = last_position -( len(part) + 2)
                        #break  # Stop processing further on error
        
                        # Extract the remaining string from the last successful position to the end
                        remainder += s[last_position:]
    
        return dictionaries, remainder


    def _read_loop(self):
        """Read data from serial port and add it to the queue."""
        while self.alive:
            if self.serial_port.in_waiting:
                #with self.serial_io_lock:
                data = self.serial_port.read(self.serial_port.in_waiting)
                self.data_queue.put(data)
            time.sleep(0.05)  # Short delay to prevent CPU overuse

    def _process_data(self):
        """Process data in a separate thread."""
        accumulatedRemainder = ""
        while self.alive:
            data = self.data_queue.get()
            try:
                #print(data.decode('utf-8'), end='', flush=True)
                data = data.decode('utf-8')
                data = data.replace('\t', '').replace('\n', '').replace('\r', '') # Remove whitespace characters - better formatting should do better?
                dictionaries, remainder = self.extract_json_objects(accumulatedRemainder + data)
                accumulatedRemainder += remainder
                print(accumulatedRemainder)
                #print(dictionaries)
                for dictionary in dictionaries:
                    if "qid" in dictionary:
                        self.queueFinalizedQueryIDs.append(abs(dictionary["qid"]))
                    else:
                        print(f"Dictionary does not contain 'qid': {dictionary}")

            except Exception as e:
                print(f"Failed to decode data: {data}. Error: {e}")
            time.sleep(0.05)  # Short delay to prevent CPU overuse
                
                
    def write_data(self, data):
        """Send data to the serial port."""
        #with self.serial_io_lock:
        self.serial_port.write(data.encode('utf-8'))
        self.serial_port.flush() # Ensure data is sent immediately
            
    def send_message(self, data, mTimeout=2, blocking=True):
        try:cqid = json.loads(data)["qid"]
        except: blocking = False
        print (f"Sending message: {cqid}, blocking: {blocking}, message length: {len(data)}")
        self.write_data(data)
        # wait for the response
        cTime = time.time()
        while blocking:
            try:
                if time.time() - cTime > mTimeout:
                    print(f"Timeout of {mTimeout} seconds reached.")
                    break
                # compare with any received responses
                qids = self.queueFinalizedQueryIDs.get()
                if cqid in qids:
                    print(f"Received response for query ID: {cqid}")
                    break
                time.sleep(0.05)
            except queue.Empty:
                #print("Waiting for response...")
                pass
        

# Example of using SimpleSerialComm
#python /Users/bene/mambaforge/envs/imswitch/lib/python3.9/site-packages/serial/tools/miniterm.py /dev/cu.SLAB_USBtoUART 500000

if __name__ == '__main__':
    port = "/dev/cu.SLAB_USBtoUART"
    baudrate = 115200# 500000
    # scan all available ports
    from serial.tools import list_ports
    port = None
    for mPort in list_ports.comports():
        # if port starts with /dev/cu.SLAB_USBtoUART, /dev/ttyUSB0, /dev/cu
        if mPort.device.startswith("/dev/cu.SLAB_USBtoUART") or mPort.device.startswith("/dev/ttyUSB0") or mPort.device.startswith("/dev/cu.wc"):
            port = mPort.device
            print(f"Found port: {port}")
            break
    
    
    comm = SimpleSerialComm(port, baudrate)
    try:
        comm.start_reading()
        
        cqid = 0
        mTimeout = 10
        while True:
            
            # short test
            message = '{"task":"/notor_act", "motor": { "steppers": [ { "stepperid": 1, "position": 1000, "speed": 5000, "isabs": 0, "isaccel":0}, { "stepperid": 2, "position": 1000, "speed": 5000, "isabs": 0, "isaccel":0}]}, "qid":'+str(cqid)+'}' 
            comm.send_message(data=message)
            cqid += 1
            
            # long test split  
            message1 = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 0, "r": 22, "g": 45, "b": 29}, {"id": 1, "r": 12, "g": 34, "b": 22}, {"id": 2, "r": 34, "g": 11, "b": 50}, {"id": 3, "r": 32, "g": 22, "b": 2}, {"id": 4, "r": 37, "g": 1, "b": 35}, {"id": 5, "r": 21, "g": 10, "b": 28}, {"id": 6, "r": 52, "g": 16, "b": 5}, {"id": 7, "r": 2, "g": 43, "b": 29}, {"id": 8, "r": 42, "g": 2, "b": 39}, {"id": 9, "r": 21, "g": 21, "b": 22}, {"id": 10, "r": 44, "g": 28, "b": 35}, {"id": 11, "r": 31, "g": 40, "b": 52}, {"id": 12, "r": 25, "g": 45, "b": 15}, {"id": 13, "r": 20, "g": 24, "b": 1}, {"id": 14, "r": 49, "g": 48, "b": 37}, {"id": 15, "r": 54, "g": 3, "b": 41}, {"id": 16, "r": 14, "g": 17, "b": 16}, {"id": 17, "r": 48, "g": 31, "b": 47}, {"id": 18, "r": 43, "g": 24, "b": 10}, {"id": 19, "r": 23, "g": 28, "b": 54}]}, "qid": '+str(cqid)+'}'
            cqid += 1
            message2 = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 28, "r": 18, "g": 6, "b": 28}, {"id": 29, "r": 14, "g": 47, "b": 5}, {"id": 30, "r": 2, "g": 31, "b": 24}, {"id": 31, "r": 53, "g": 8, "b": 50}, {"id": 32, "r": 1, "g": 15, "b": 14}, {"id": 33, "r": 19, "g": 18, "b": 39}, {"id": 34, "r": 44, "g": 22, "b": 29}, {"id": 35, "r": 4, "g": 38, "b": 9}, {"id": 36, "r": 1, "g": 28, "b": 54}, {"id": 37, "r": 37, "g": 43, "b": 22}, {"id": 38, "r": 14, "g": 27, "b": 27}, {"id": 39, "r": 22, "g": 10, "b": 49}, {"id": 40, "r": 32, "g": 29, "b": 39}, {"id": 41, "r": 14, "g": 2, "b": 41}, {"id": 42, "r": 39, "g": 37, "b": 35}, {"id": 43, "r": 26, "g": 44, "b": 32}, {"id": 44, "r": 45, "g": 19, "b": 53}, {"id": 45, "r": 44, "g": 26, "b": 37}, {"id": 46, "r": 40, "g": 28, "b": 11}, {"id": 47, "r": 9, "g": 4, "b": 23}, {"id": 48, "r": 41, "g": 22, "b": 31}, {"id": 49, "r": 10, "g": 5, "b": 46}, {"id": 50, "r": 48, "g": 39, "b": 52}, {"id": 51, "r": 33, "g": 15, "b": 26}, {"id": 52, "r": 50, "g": 19, "b": 44}, {"id": 53, "r": 34, "g": 18, "b": 35}, {"id": 54, "r": 6, "g": 0, "b": 39}, {"id": 55, "r": 6, "g": 26, "b": 43}, {"id": 56, "r": 24, "g": 35, "b": 21}, {"id": 57, "r": 47, "g": 8, "b": 31}, {"id": 58, "r": 1, "g": 0, "b": 32}, {"id": 59, "r": 52, "g": 12, "b": 28}, {"id": 60, "r": 39, "g": 53, "b": 5}, {"id": 61, "r": 6, "g": 32, "b": 41}, {"id": 62, "r": 28, "g": 0, "b": 24}, {"id": 63, "r": 34, "g": 46, "b": 27}]}, "qid": '+str(cqid)+'}'
            cqid += 1
            
            messages = [message1, message2]
            
            for message in messages:
                comm.send_message(data=message, blocking=True)
            
            # very short test
            message = '{"task": "/state_get", "qid": '+str(cqid)+'}'
            comm.send_message(data=message)
            cqid += 1
            
    finally:
        comm.stop_reading()
