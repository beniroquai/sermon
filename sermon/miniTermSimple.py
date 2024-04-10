import threading
import serial
import time
import json
import queue
class SimpleSerialComm:
    def __init__(self, port, baudrate=9600):
        self.serial_port = serial.Serial(port, baudrate=baudrate, timeout=0)
        self.alive = False
        self.read_thread = None
        maxQentries = 100
        self.queueFinalizedQueryIDs = queue.Queue(maxQentries)

    def start_reading(self):
        """Start reading serial port in a separate thread."""
        if not self.alive:
            self.alive = True
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.start()

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
                    print(f"Failed to decode JSON: {json_str}. Error: {e}")
                    break  # Stop processing further on error
        
        # Extract the remaining string from the last successful position to the end
        remainder = s[last_position:]
    
        return dictionaries, remainder

    def _read_loop(self):
        """Read data from serial port and print it."""
        latestDictionary = ""
        recordingDictionary = False
        lineCounter = 0
        accumulatedRemainder = ""
        
        while self.alive:
            if self.serial_port.in_waiting:
                data = self.serial_port.read(self.serial_port.in_waiting)
                try:
                    print(data.decode('utf-8'), end='', flush=True)
                    data = data.decode('utf-8')
                    data = data.replace('\t', '').replace('\n', '').replace('\r', '')
                    dictionaries, remainder = self.extract_json_objects(accumulatedRemainder + data)
                    accumulatedRemainder += remainder
                    print(dictionaries)
                    for dictionary in dictionaries:
                        if "qid" in dictionary:
                            self.queueFinalizedQueryIDs.put(dictionary["qid"])
                        else:
                            print(f"Dictionary does not contain 'qid': {dictionary}")
                    
                except Exception as e:
                    print(f"Failed to decode data: {data}. Error: {e}")
                    pass
            time.sleep(0.1)  # Short delay to prevent CPU overuse

    def write_data(self, data):
        """Send data to the serial port."""
        self.serial_port.write(data.encode('utf-8'))
        
    def send_message(self, message, cqid, mTimeout=2):
        print (f"Sending message: {message}")
        self.write_data(message)
        # wait for the response
        cTime = time.time()
        while True:
            try:
                if time.time() - cTime > mTimeout:
                    print(f"Timeout of {mTimeout} seconds reached.")
                    break
                qid = self.queueFinalizedQueryIDs.get(timeout=1)
                print(f"Received response for query ID: {qid}")
                if qid == cqid:
                    break
            except queue.Empty:
                print("Waiting for response...")
                pass
        

# Example of using SimpleSerialComm
#python /Users/bene/mambaforge/envs/imswitch/lib/python3.9/site-packages/serial/tools/miniterm.py /dev/cu.SLAB_USBtoUART 500000

if __name__ == '__main__':
    port = "/dev/cu.SLAB_USBtoUART"
    baudrate = 500000
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
            message = '{"task": "/ledarr_act", "led": {"LEDArrMode": 1, "led_array": [{"id": 0, "r": 0, "g": 0, "b": 0}]}, "qid": '+str(cqid)+'}' 
            comm.send_message(message=message, cqid=cqid)
            cqid += 1
            
            # long test
            message = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 0, "r": 22, "g": 45, "b": 29}, {"id": 1, "r": 12, "g": 34, "b": 22}, {"id": 2, "r": 34, "g": 11, "b": 50}, {"id": 3, "r": 32, "g": 22, "b": 2}, {"id": 4, "r": 37, "g": 1, "b": 35}, {"id": 5, "r": 21, "g": 10, "b": 28}, {"id": 6, "r": 52, "g": 16, "b": 5}, {"id": 7, "r": 2, "g": 43, "b": 29}, {"id": 8, "r": 42, "g": 2, "b": 39}, {"id": 9, "r": 21, "g": 21, "b": 22}, {"id": 10, "r": 44, "g": 28, "b": 35}, {"id": 11, "r": 31, "g": 40, "b": 52}, {"id": 12, "r": 25, "g": 45, "b": 15}, {"id": 13, "r": 20, "g": 24, "b": 1}, {"id": 14, "r": 49, "g": 48, "b": 37}, {"id": 15, "r": 54, "g": 3, "b": 41}, {"id": 16, "r": 14, "g": 17, "b": 16}, {"id": 17, "r": 48, "g": 31, "b": 47}, {"id": 18, "r": 43, "g": 24, "b": 10}, {"id": 19, "r": 23, "g": 28, "b": 54}, {"id": 20, "r": 42, "g": 54, "b": 38}, {"id": 21, "r": 32, "g": 51, "b": 4}, {"id": 22, "r": 31, "g": 38, "b": 5}, {"id": 23, "r": 41, "g": 0, "b": 8}, {"id": 24, "r": 26, "g": 6, "b": 44}, {"id": 25, "r": 41, "g": 30, "b": 0}, {"id": 26, "r": 48, "g": 13, "b": 14}, {"id": 27, "r": 48, "g": 52, "b": 24}, {"id": 28, "r": 18, "g": 6, "b": 28}, {"id": 29, "r": 14, "g": 47, "b": 5}, {"id": 30, "r": 2, "g": 31, "b": 24}, {"id": 31, "r": 53, "g": 8, "b": 50}, {"id": 32, "r": 1, "g": 15, "b": 14}, {"id": 33, "r": 19, "g": 18, "b": 39}, {"id": 34, "r": 44, "g": 22, "b": 29}, {"id": 35, "r": 4, "g": 38, "b": 9}, {"id": 36, "r": 1, "g": 28, "b": 54}, {"id": 37, "r": 37, "g": 43, "b": 22}, {"id": 38, "r": 14, "g": 27, "b": 27}, {"id": 39, "r": 22, "g": 10, "b": 49}, {"id": 40, "r": 32, "g": 29, "b": 39}, {"id": 41, "r": 14, "g": 2, "b": 41}, {"id": 42, "r": 39, "g": 37, "b": 35}, {"id": 43, "r": 26, "g": 44, "b": 32}, {"id": 44, "r": 45, "g": 19, "b": 53}, {"id": 45, "r": 44, "g": 26, "b": 37}, {"id": 46, "r": 40, "g": 28, "b": 11}, {"id": 47, "r": 9, "g": 4, "b": 23}, {"id": 48, "r": 41, "g": 22, "b": 31}, {"id": 49, "r": 10, "g": 5, "b": 46}, {"id": 50, "r": 48, "g": 39, "b": 52}, {"id": 51, "r": 33, "g": 15, "b": 26}, {"id": 52, "r": 50, "g": 19, "b": 44}, {"id": 53, "r": 34, "g": 18, "b": 35}, {"id": 54, "r": 6, "g": 0, "b": 39}, {"id": 55, "r": 6, "g": 26, "b": 43}, {"id": 56, "r": 24, "g": 35, "b": 21}, {"id": 57, "r": 47, "g": 8, "b": 31}, {"id": 58, "r": 1, "g": 0, "b": 32}, {"id": 59, "r": 52, "g": 12, "b": 28}, {"id": 60, "r": 39, "g": 53, "b": 5}, {"id": 61, "r": 6, "g": 32, "b": 41}, {"id": 62, "r": 28, "g": 0, "b": 24}, {"id": 63, "r": 34, "g": 46, "b": 27}]}, "qid": '+str(cqid)+'}'
            comm.send_message(message=message, cqid=cqid)
            cqid += 1
            
    finally:
        comm.stop_reading()
