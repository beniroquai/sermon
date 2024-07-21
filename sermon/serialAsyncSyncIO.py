import asyncio
import serial
import json
from collections import deque
from serial.tools import list_ports
import logging
import time
from asynciohelper import *

T_SERIAL_WARMUP = .5

class RingBuffer(deque):
    def __init__(self, size_max):
        super().__init__(maxlen=size_max)

    def append(self, datum):
        super().append(datum)
        return self

    def get(self):
        return list(self)

class Serial:
    def __init__(self, port, baudrate=115200, timeout=5, identity="UC2_Feather", parent=None, DEBUG=False):
        self.baudrate = baudrate
        self.timeout = timeout
        self.identity = identity
        self.DEBUG = DEBUG
        self._parent = parent
        self.serial_port_name = port
        self.serial_device = None
        self.is_connected = False
        self.resetLastCommand = False
        self.data_queue = asyncio.Queue()
        self.maxQentries = 100
        self.queueFinalizedQueryIDs = RingBuffer(self.maxQentries)
        self.identifier_counter = 0
        self.responses = {}
        self.isReadingLoopRunning = False
        self.isWritingLoopRunning = False

        self.callBackList = []

        if self._parent is None:
            self._logger = logging.getLogger(__name__)
            self._logger.setLevel(logging.DEBUG)
            self._logger.addHandler(logging.StreamHandler())
        else:
            self._logger = self._parent.logger

        # Ensure the event loop is running
        
        # Ensure the event loop is running
        self.loop = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._ensure_event_loop()
        
        # Convert async methods to sync
        self.open_sync = convert_async_to_sync(self.open, self.loop, self.executor)
        self.send_message_sync = convert_async_to_sync(self.sendMessage, self.loop, self.executor)

    def open_sync(self, port=None, baudrate=None):
        self._ensure_event_loop()
        if baudrate is None:
            baudrate = self.baudrate
        self.serial_device = self.openDevice(port, baudrate)
        self.is_connected = True
        self.start_reading_sync()

    def send_message_sync(self, data: str, nResponses: int = 1, mTimeout: float = 20.0, blocking: bool = True):
        self._ensure_event_loop()
        return asyncio.run_coroutine_threadsafe(self.sendMessage(data, nResponses, mTimeout, blocking), self.loop).result()

    def _ensure_event_loop(self):
        if not self.loop or not self.loop.is_running():
            self.loop = asyncio.new_event_loop()
            self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self.loop_thread.start()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def open(self, port=None, baudrate=None):
        if baudrate is None:
            baudrate = self.baudrate
        self.serial_device = await asyncio.get_event_loop().run_in_executor(None, self.openDevice, port, baudrate)
        self.is_connected = True
        await self.start_reading()

    def close(self):
        self.stop_reading()
        self.closeDevice()
        
    def closeDevice(self):
        if self.serial_port_name is not None:
            try:
                self.serial_device.close()
            except Exception as e:
                self._logger.error("[CloseDevice]: " + str(e))

    def openDevice(self, port=None, baudrate=115200):
        if hasattr(self, "serial_port_name") and self.serial_device is not None:
            self.closeDevice()

        if port is not None:
            isUC2, serial_device = self.tryToConnect(port=port)
            if isUC2:
                self.is_connected = True
        
        if port is None or not isUC2:
            serial_device = self.findCorrectSerialDevice()
            if serial_device is None:
                from MockSerial import MockSerial
                serial_device = MockSerial(port, baudrate, timeout=.1)
                self.is_connected = False

        return serial_device

    def findCorrectSerialDevice(self):
        _available_ports = list_ports.comports(include_links=False)
        ports_to_check = ["COM", "/dev/tt", "/dev/a", "/dev/cu.SLA", "/dev/cu.wchusb"]
        descriptions_to_check = ["CH340", "CP2102"]

        for port in _available_ports:
            if any(port.device.startswith(allowed_port) for allowed_port in ports_to_check) or \
               any(port.description.startswith(allowed_description) for allowed_description in descriptions_to_check):
                isUC2, serial_device = self.tryToConnect(port.device)
                if isUC2:
                    self.manufacturer = port.manufacturer
                    return serial_device

        self.is_connected = False
        self.serialport = "NotConnected"
        self._logger.debug("No USB device connected! Using DUMMY!")
        self.manufacturer = "UC2Mock"
        return None

    def tryToConnect(self, port):
        try:
            serial_device = serial.Serial(port=port, baudrate=self.baudrate, timeout=0)
            time.sleep(T_SERIAL_WARMUP)
            mBufferCode = self.freeSerialBuffer(serial_device)
            if mBufferCode == 1:
                return True, serial_device
            if self.checkFirmware(serial_device):
                self.NumberRetryReconnect = 0
                return True, serial_device
            else:
                return False, None
        except Exception as e:
            self._logger.debug(f"Trying out port {port} failed: " + str(e))

        return False, None

    def freeSerialBuffer(self, serial_device, timeout=4, nLinesWait=1000, nEmptyLinesUntilBreak=10):
        nEmptyLines = 0
        cTime = time.time()
        for _ in range(nLinesWait):
            if serial_device.in_waiting:
                mLine = serial_device.read(serial_device.in_waiting)
                if self.DEBUG: self._logger.debug(mLine)
                if mLine == b"":
                    nEmptyLines += 1
                if nEmptyLines > nEmptyLinesUntilBreak:
                    return 2
                if b"setup':'done" in mLine:
                    return 1
                
            if time.time() - cTime > timeout:
                return 0
            time.sleep(0.02)

    def checkFirmware(self, ser, nMaxLineRead=500):
        path = "/state_get"
        payload = {"task": path}
        if self.DEBUG: self._logger.debug("[checkFirmware]: " + str(payload))
        ser.write(json.dumps(payload).encode('utf-8'))
        ser.write(b'\n')
        ser.flush()
            
        for i in range(nMaxLineRead):
            if ser.in_waiting:
                mLine = ser.read(ser.in_waiting)
                if self.DEBUG and mLine != "": self._logger.debug("[checkFirmware]: " + str(mLine))
                if mLine.decode('utf-8').strip() == "++":
                    self.freeSerialBuffer(ser)
                    return True
        return False

    def _generate_identifier(self):
        self.identifier_counter += 1
        return self.identifier_counter

    def breakCurrentCommunication(self):
        self.resetLastCommand = True

    async def start_reading(self):
        if self.is_connected:
            if not self.isReadingLoopRunning:
                asyncio.create_task(self._read_loop())
            if not self.isWritingLoopRunning:
                asyncio.create_task(self._process_data())

    def stop_reading(self):
        self.is_connected = False
        if self.serial_device.is_open:
            self.serial_device.close()

    def extract_json_objects(self, s):
        parts = s.split('++')
        dictionaries = []
        last_position = 0
        remainder = ""
        for part in parts:
            json_str = part.split('--')[0].strip()
            if json_str:
                try:
                    last_position += len(part) + 2
                    json_dict = json.loads(json_str)
                    dictionaries.append(json_dict)
                except json.JSONDecodeError as e:
                    try:
                        import re
                        match = re.search(r'"qid":(\d+)', json_str)
                        if match:
                            qid = int(match.group(1))
                            json_dict = {"qid": qid}
                            dictionaries.append(json.loads(json.dumps(json_dict)))
                    except Exception as e:
                        self._logger.debug(f"Failed to decode JSON: {json_str}. Error: {e}")
                        last_position -= len(part) + 2
                        remainder += s[last_position:]
    
        return dictionaries, remainder

    async def _read_loop(self):
        self.isReadingLoopRunning = True
        while self.is_connected:
            if self.serial_device.in_waiting > 0:
                data = await asyncio.get_event_loop().run_in_executor(None, self.serial_device.read, self.serial_device.in_waiting)
                if data:
                    await self.data_queue.put(data)
            await asyncio.sleep(0.05)
        self.isReadingLoopRunning = False

    async def _process_data(self):
        accumulatedRemainder = ""
        self.isWritingLoopRunning = True
        while self.is_connected:
            data = await self.data_queue.get()
            try:
                data = data.decode('utf-8')
                data = data.replace('\t', '').replace('\n', '').replace('\r', '')
                
                if "reboot" in data:
                    self._logger.warning("Device rebooted")
                    self.resetLastCommand = True
                    continue
                
                dictionaries, remainder = self.extract_json_objects(accumulatedRemainder + data)
                accumulatedRemainder += remainder
                self._logger.debug(accumulatedRemainder)
                for dictionary in dictionaries:
                    if "qid" in dictionary:
                        self.queueFinalizedQueryIDs.append(dictionary["qid"])
                        if dictionary["qid"] in self.responses:
                            self.responses[dictionary["qid"]].append(dictionary)
                        else:
                            self.responses[dictionary["qid"]] = [dictionary]
                            
                        if self.DEBUG: 
                            self._logger.debug(f"Received response for query ID: {dictionary['qid'], dictionary}")
                        
                        if len(self.callBackList) > 0:
                            for callback in self.callBackList:
                                try:
                                    if callback["pattern"] in dictionary:
                                        callback["callbackfct"](dictionary)
                                except Exception as e:
                                    self._logger.error("[ProcessCommands]: " + str(e))
                    else:
                        self._logger.debug(f"Dictionary does not contain 'qid': {dictionary}")

            except Exception as e:
                self._logger.debug(f"Failed to decode data: {data}. Error: {e}")
            await asyncio.sleep(0.05)
        self.isWritingLoopRunning = False

    def register_callback(self, callback, pattern):
        self.callBackList.append({"callbackfct": callback, "pattern": pattern})

    async def write_data(self, data: str):
        if self.DEBUG: self._logger.debug(f"Writing data: {data}")
        await asyncio.get_event_loop().run_in_executor(None, self.serial_device.write, data.encode('utf-8'))
        await asyncio.get_event_loop().run_in_executor(None, self.serial_device.flush)

    async def sendMessage(self, data: str, nResponses: int = 1, mTimeout: float = 20.0, blocking: bool = True):
        if type(data) == str:
            data = json.loads(data)
        try:
            cqid = data["qid"]
            self.identifier_counter = cqid
        except:
            cqid = self._generate_identifier()
        if self.DEBUG: self._logger.debug(f"Sending message: {cqid}, blocking: {blocking}, message length: {len(data)}")
        await self.write_data(json.dumps(data))
        cTime = time.time()

        if nResponses == 0 or mTimeout <= 0 or not blocking:
            blocking = False
            await asyncio.sleep(0.1)
            return cqid

        while blocking:
            try:
                if time.time() - cTime > mTimeout:
                    self._logger.debug(f"Timeout of {mTimeout} seconds reached for QID: {cqid}.")
                    break
                qids = self.queueFinalizedQueryIDs.get()
                if cqid in qids and qids.count(cqid) >= nResponses:
                    await asyncio.sleep(0.15)  # let the serial settle for a bit
                    return self.responses[cqid]
                if -cqid in qids:
                    self._logger.debug("You have sent the wrong command!")
                    return "Wrong Command"
            except queue.Empty:
                pass
            await asyncio.sleep(0.05)

    async def get_json(self, path, timeout=1):
        message = {"task": path}
        message = json.dumps(message)
        return await self.sendMessage(message, nResponses=0, mTimeout=timeout)

    async def post_json(self, path, payload, getReturn=True, nResponses=1, timeout=100):
        if payload is None:
            payload = {}
        if "task" not in payload:
            payload["task"] = path

        if not getReturn:
            nResponses = -1
        if self.cmdCallBackFct is not None:
            self.cmdCallBackFct(payload)
            return "OK"
        else:
            return await self.sendMessage(data=payload, nResponses=nResponses, mTimeout=timeout, blocking=getReturn)


# Example of using SimpleSerialComm
async def main():
    port = "/dev/cu.SLAB_USBtoUART"
    baudrate = 115200
    mSerial = Serial(port, baudrate, DEBUG=1)
    await mSerial.open(port, baudrate)
    
    cqid = 0
    mTimeout = 10
    while True:
        message = '{"task":"/motor_act", "motor": { "steppers": [ { "stepperid": 1, "position": 100, "speed": 5000, "isabs": 0, "isaccel":0}, { "stepperid": 2, "position": 1000, "speed": 5000, "isabs": 0, "isaccel":0}]}, "qid":' + str(cqid) + '}'
        await mSerial.sendMessage(data=message, mTimeout=10)
        cqid += 1
        
        message1 = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 0, "r": 22, "g": 45, "b": 29}, {"id": 1, "r": 12, "g": 34, "b": 22}, {"id": 2, "r": 34, "g": 11, "b": 50}, {"id": 3, "r": 32, "g": 22, "b": 2}, {"id": 4, "r": 37, "g": 1, "b": 35}, {"id": 5, "r": 21, "g": 10, "b": 28}, {"id": 6, "r": 52, "g": 16, "b": 5}, {"id": 7, "r": 2, "g": 43, "b": 29}, {"id": 8, "r": 42, "g": 2, "b": 39}, {"id": 9, "r": 21, "g": 21, "b": 22}, {"id": 10, "r": 44, "g": 28, "b": 35}, {"id": 11, "r": 31, "g": 40, "b": 52}, {"id": 12, "r": 25, "g": 45, "b": 15}, {"id": 13, "r": 20, "g": 24, "b": 1}, {"id": 14, "r": 49, "g": 48, "b": 37}, {"id": 15, "r": 54, "g": 3, "b": 41}, {"id": 16, "r": 14, "g": 17, "b": 16}, {"id": 17, "r": 48, "g": 31, "b": 47}, {"id": 18, "r": 43, "g": 24, "b": 10}, {"id": 19, "r": 23, "g": 28, "b": 54}]}, "qid": ' + str(cqid) + '}'
        await mSerial.sendMessage(data=message, mTimeout=10)
        cqid += 1

        message2 = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 28, "r": 18, "g": 6, "b": 28}, {"id": 29, "r": 14, "g": 47, "b": 5}, {"id": 30, "r": 2, "g": 31, "b": 24}, {"id": 31, "r": 53, "g": 8, "b": 50}, {"id": 32, "r": 1, "g": 15, "b": 14}, {"id": 33, "r": 19, "g": 18, "b": 39}, {"id": 34, "r": 44, "g": 22, "b": 29}, {"id": 35, "r": 4, "g": 38, "b": 9}, {"id": 36, "r": 1, "g": 28, "b": 54}, {"id": 37, "r": 37, "g": 43, "b": 22}, {"id": 38, "r": 14, "g": 27, "b": 27}, {"id": 39, "r": 22, "g": 10, "b": 49}, {"id": 40, "r": 32, "g": 29, "b": 39}, {"id": 41, "r": 14, "g": 2, "b": 41}, {"id": 42, "r": 39, "g": 37, "b": 35}, {"id": 43, "r": 26, "g": 44, "b": 32}, {"id": 44, "r": 45, "g": 19, "b": 53}, {"id": 45, "r": 44, "g": 26, "b": 37}, {"id": 46, "r": 40, "g": 28, "b": 11}, {"id": 47, "r": 9, "g": 4, "b": 23}, {"id": 48, "r": 41, "g": 22, "b": 31}, {"id": 49, "r": 10, "g": 5, "b": 46}, {"id": 50, "r": 48, "g": 39, "b": 52}, {"id": 51, "r": 33, "g": 15, "b": 26}, {"id": 52, "r": 50, "g": 19, "b": 44}]}, "qid": ' + str(cqid) + '}'
        await mSerial.sendMessage(data=message, mTimeout=10)
        cqid += 1

        message3 = '{"task":"/state_get", "heap":1, "qid": ' + str(cqid) + '}'
        await mSerial.sendMessage(data=message, mTimeout=10)
        cqid += 1

        message = '{"task": "/state_get", "qid": ' + str(cqid) + '}'
        await mSerial.sendMessage(data=message, blocking=False)
        cqid += 1

if __name__ == '__main__':
    if 0:
        asyncio.run(main())
    else:
        port = "/dev/cu.SLAB_USBtoUART"
        baudrate = 115200
        mSerial = Serial(port, baudrate, DEBUG=1)
        
        # Ensure the event loop is running for synchronous execution
        mSerial.open_sync(port, baudrate)
        
        mSerial.send_message_sync('{"task":"/motor_act", "motor": { "steppers": [ { "stepperid": 1, "position": 1000, "speed": 5000, "isabs": 0, "isaccel":0}, { "stepperid": 2, "position": 1000, "speed": 5000, "isabs": 0, "isaccel":0}]}, "qid":1}', blocking=True, mTimeout=10)
