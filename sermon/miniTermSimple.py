import threading
import serial
import time

class SimpleSerialComm:
    def __init__(self, port, baudrate=9600):
        self.serial_port = serial.Serial(port, baudrate=baudrate, timeout=0)
        self.alive = False
        self.read_thread = None

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

    def _read_loop(self):
        """Read data from serial port and print it."""
        while self.alive:
            if self.serial_port.in_waiting:
                data = self.serial_port.read(self.serial_port.in_waiting)
                try:print(data.decode('utf-8'), end='', flush=True)
                except:pass
            time.sleep(0.1)  # Short delay to prevent CPU overuse

    def write_data(self, data):
        """Send data to the serial port."""
        self.serial_port.write(data.encode('utf-8'))

# Example of using SimpleSerialComm
#python /Users/bene/mambaforge/envs/imswitch/lib/python3.9/site-packages/serial/tools/miniterm.py /dev/cu.SLAB_USBtoUART 500000

if __name__ == '__main__':
    port = "/dev/cu.SLAB_USBtoUART"
    baudrate = 500000
    comm = SimpleSerialComm(port, baudrate)
    try:
        comm.start_reading()
        while True:

            message = '{"task": "/ledarr_act", "led": {"LEDArrMode": 1, "led_array": [{"id": 0, "r": 0, "g": 0, "b": 0}]}, "qid": 1}' 
            comm.write_data(message)
            time.sleep(0.1)
            message = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 0, "r": 22, "g": 45, "b": 29}, {"id": 1, "r": 12, "g": 34, "b": 22}, {"id": 2, "r": 34, "g": 11, "b": 50}, {"id": 3, "r": 32, "g": 22, "b": 2}, {"id": 4, "r": 37, "g": 1, "b": 35}, {"id": 5, "r": 21, "g": 10, "b": 28}, {"id": 6, "r": 52, "g": 16, "b": 5}, {"id": 7, "r": 2, "g": 43, "b": 29}, {"id": 8, "r": 42, "g": 2, "b": 39}, {"id": 9, "r": 21, "g": 21, "b": 22}, {"id": 10, "r": 44, "g": 28, "b": 35}, {"id": 11, "r": 31, "g": 40, "b": 52}, {"id": 12, "r": 25, "g": 45, "b": 15}, {"id": 13, "r": 20, "g": 24, "b": 1}, {"id": 14, "r": 49, "g": 48, "b": 37}, {"id": 15, "r": 54, "g": 3, "b": 41}, {"id": 16, "r": 14, "g": 17, "b": 16}, {"id": 17, "r": 48, "g": 31, "b": 47}, {"id": 18, "r": 43, "g": 24, "b": 10}, {"id": 19, "r": 23, "g": 28, "b": 54}, {"id": 20, "r": 42, "g": 54, "b": 38}, {"id": 21, "r": 32, "g": 51, "b": 4}, {"id": 22, "r": 31, "g": 38, "b": 5}, {"id": 23, "r": 41, "g": 0, "b": 8}, {"id": 24, "r": 26, "g": 6, "b": 44}, {"id": 25, "r": 41, "g": 30, "b": 0}, {"id": 26, "r": 48, "g": 13, "b": 14}, {"id": 27, "r": 48, "g": 52, "b": 24}, {"id": 28, "r": 18, "g": 6, "b": 28}, {"id": 29, "r": 14, "g": 47, "b": 5}, {"id": 30, "r": 2, "g": 31, "b": 24}, {"id": 31, "r": 53, "g": 8, "b": 50}, {"id": 32, "r": 1, "g": 15, "b": 14}, {"id": 33, "r": 19, "g": 18, "b": 39}, {"id": 34, "r": 44, "g": 22, "b": 29}, {"id": 35, "r": 4, "g": 38, "b": 9}, {"id": 36, "r": 1, "g": 28, "b": 54}, {"id": 37, "r": 37, "g": 43, "b": 22}, {"id": 38, "r": 14, "g": 27, "b": 27}, {"id": 39, "r": 22, "g": 10, "b": 49}, {"id": 40, "r": 32, "g": 29, "b": 39}, {"id": 41, "r": 14, "g": 2, "b": 41}, {"id": 42, "r": 39, "g": 37, "b": 35}, {"id": 43, "r": 26, "g": 44, "b": 32}, {"id": 44, "r": 45, "g": 19, "b": 53}, {"id": 45, "r": 44, "g": 26, "b": 37}, {"id": 46, "r": 40, "g": 28, "b": 11}, {"id": 47, "r": 9, "g": 4, "b": 23}, {"id": 48, "r": 41, "g": 22, "b": 31}, {"id": 49, "r": 10, "g": 5, "b": 46}, {"id": 50, "r": 48, "g": 39, "b": 52}, {"id": 51, "r": 33, "g": 15, "b": 26}, {"id": 52, "r": 50, "g": 19, "b": 44}, {"id": 53, "r": 34, "g": 18, "b": 35}, {"id": 54, "r": 6, "g": 0, "b": 39}, {"id": 55, "r": 6, "g": 26, "b": 43}, {"id": 56, "r": 24, "g": 35, "b": 21}, {"id": 57, "r": 47, "g": 8, "b": 31}, {"id": 58, "r": 1, "g": 0, "b": 32}, {"id": 59, "r": 52, "g": 12, "b": 28}, {"id": 60, "r": 39, "g": 53, "b": 5}, {"id": 61, "r": 6, "g": 32, "b": 41}, {"id": 62, "r": 28, "g": 0, "b": 24}, {"id": 63, "r": 34, "g": 46, "b": 27}]}, "qid": 2}'
            comm.write_data(message)
            time.sleep(0.1)
            
            
    finally:
        comm.stop_reading()
