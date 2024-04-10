# -*- coding: utf-8 -*-

"""
The main application run loop.
"""

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import division

import os
import sys
if os.name == 'nt':
    print('sermon is not compatabile with Windows.')
    sys.exit()

import threading
import re
import time
import argparse

import serial
import urwid

import sermon
import sermon.util as util
from sermon.magics import magic
from sermon.resources import help_status_str



parity_values = {'none': serial.PARITY_NONE,
                 'even': serial.PARITY_EVEN,
                 'odd': serial.PARITY_ODD,
                 'mark': serial.PARITY_MARK,
                 'space': serial.PARITY_SPACE}

stopbits_values = {'1': serial.STOPBITS_ONE,
                   '1.5': serial.STOPBITS_ONE_POINT_FIVE,
                   '2': serial.STOPBITS_TWO}


class ConsoleEdit(urwid.Edit):
    def __init__(self, callback, *args, **kwargs):
        super(ConsoleEdit, self).__init__(*args, **kwargs)
        self.callback = callback
        self.history = []
        self.history_pos = 0

    def keypress(self, size, key):
        if key == 'enter':
            self.callback(self.edit_text)
            self.history.append(self.edit_text)
            self.history_pos = 0
            self.set_edit_text('')
            return False
        elif key == 'up':
            # Cycle backwards in history, unless already as far back as we can
            # go.
            if self.history_pos == len(self.history):
                # Already as far as we can go in history.
                util.beep()
                return
            self.history_pos = util.limit(self.history_pos + 1,
                                          1, len(self.history))
            self.set_edit_text(
                self.history[-self.history_pos])
            self.set_edit_pos(len(self.edit_text))
        elif key == 'down':
            # Cycle forwards in history.
            if self.history_pos == 1:
                self.history_pos = 0
                return False
            elif self.history_pos == 0:
                util.beep()
                return

            self.history_pos = util.limit(self.history_pos - 1,
                                          1, len(self.history))
            self.set_edit_text(
                self.history[-self.history_pos])
            self.set_edit_pos(len(self.edit_text))
            return
        else:
            return super(ConsoleEdit, self).keypress(size, key)


class ScrollingTextOverlay(urwid.Overlay):
    def __init__(self, content, bottom_widget):
        """
        Parameters
        ----------
        content : str
            The contents to display in the overlay widget.
        bottom_widget : urwid.Widget
            The original widget that the overlay appears over.
        """
        listbox = urwid.ListBox([urwid.Text(content)])
        frame = urwid.Frame(listbox,
                            header=urwid.AttrMap(
                                urwid.Text(help_status_str), 'statusbar'))

        super(ScrollingTextOverlay, self).__init__(
            frame, bottom_widget,
            align='center', width=('relative', 100),
            valign='top', height=('relative', 100),
            left=0, right=0,
            top=0, bottom=0)

    def keypress(self, size, key):
        if key == 'j':
            key = 'down'
        elif key == 'k':
            key = 'up'
        elif key == 'ctrl d':
            key = 'page down'
        elif key == 'ctrl u':
            key = 'page up'
        return super(ScrollingTextOverlay, self).keypress(size, key)


class Sermon(object):
    """
    The main serial monitor class. Starts a read thread that polls the serial
    device and prints results to top window. Sends commands to serial device
    after they have been executed in the curses textpad.
    """
    def __init__(self, device, baudrate=500000, byte_size=8, parity=None, stopbits=1, xonxoff=None, rtscts=None, dsrdtr=None):
        # Receive display widgets
        self.receive_window = urwid.Text('')
        body = urwid.ListBox([self.receive_window, urwid.Text('')])
        body.set_focus(1)

        # Draw main frame with status header and footer for commands.
        self.conection_msg = urwid.Text('', 'left')
        self.status_msg = urwid.Text('', 'right')
        self.header = urwid.Columns([self.conection_msg, self.status_msg])
        self.frame = urwid.Frame(
            body,
            header=urwid.AttrMap(self.header, 'statusbar'),
            footer=ConsoleEdit(self.send_text, ': '),
            focus_part='footer')
        palette = [
            ('error', 'light red', 'black'),
            ('ok', 'dark green', 'black'),
            ('statusbar', '', 'black')
        ]
        self.kill = False
        self.append_text = ''
        self.frame_text = ''
        self.byte_list_pattern = re.compile(
            '(\$\(([^\)]+?)\))|(\${([^\)]+?)})')
        self.device = device
        self.serial = serial.Serial(device,baudrate=baudrate,timeout=1)
        #,
        #                            bytesize=byte_size,
        #                            parity=serial.PARITY_NONE, 
        #                            stopbits=serial.STOPBITS_ONE,
        #                            xonxoff=xonxoff,#rtscts=rtscts,#dsrdtr=dsrdtr,
        #                            timeout=0.1)
        time.sleep(0.1)
        self.serial.flushInput()
        self.conection_msg.set_text(('ok', self.serial.name))

        self.worker = threading.Thread(target=self.serial_read_worker)
        self.worker.daemon = True

        self.logging = False
        self.logfile = None
        
    def update_status(self, status, text):
        self.status_msg.set_text((status, text))

    def send_text(self, edit_text):
        """
        Callback called when editing is completed (after enter is pressed)
        """
        self.serial.write(edit_text.encode('latin1'))

    def overlay(self, content):
        """
        Shows the given content in an overlay window above the main frame.

        Parameters
        ----------
        content : str
            The text content to display over the main frame.
        """
        self.loop.widget = ScrollingTextOverlay(content, self.frame)

    def received_data(self, data):
        self.receive_window.set_text(self.receive_window.text +
                                     data.decode('latin1'))
        if self.logging:
            try:
                with open(self.logfile, 'a') as f:
                    f.write(data.decode('latin1'))
            except:
                self.update_status('error', 'Error writing to logfile.')

    def serial_read_worker(self):
        """
        Reads serial device and prints results to upper curses window.
        """
        latestDictionary = ""
        recordingDictionary = False
        lineCounter = 0
        while not self.kill:
            data = self.serial.readline()
            
            if len(data) > 0:
                print(data)
                # Need to reverse \r and \n for curses, otherwise it just
                # clears the current line instead of making a new line. Also,
                # translate single \n to \n\r so curses returns to the first
                # column.
                try:
                    if data == b'\r':
                        continue
                    else:         # {"task": "/stage_get"}
                        # remove \t and \n 
                        data = data.replace(b'\t', b'').replace(b'\n', b'')
                        # convert to string
                        data = data.decode('latin1')
                        if data.find("++") != -1:
                            recordingDictionary = True
                            latestDictionary = ""
                            continue
                        if recordingDictionary:
                            if data.find("--") != -1:
                                recordingDictionary = False
                                lineCounter = 0
                                print(latestDictionary)
                                continue
                            
                            latestDictionary += data
                            lineCounter += 1
                        if lineCounter > 50:
                            recordingDictionary = False
                            lineCounter = 0
                            print(latestDictionary)
                            continue
                        #os.write(self.fd, data)
                except UnicodeEncodeError or TypeError:
                    # Handle null bytes in string.
                    raise

    def write_list_of_bytes(self, string):
        byte_data = [int(s.strip(), 0) for s in string.split(',')]
        self.serial.write(bytearray(byte_data))

    def start(self):
        self.worker.start()
        

    def stop(self):
        self.kill = True
        while self.worker.is_alive():
            pass
        self.serial.close()

    def exit(self):
        self.stop()
        raise urwid.ExitMainLoop()


def main():

    # If device is not specified, prompt user to select an available device.
    device =  "/dev/cu.wchusbserial110"  # Adjust this to your device's serial port
    device = "/dev/cu.SLAB_USBtoUART"
    baudrate = 500000


    app = Sermon(device, baudrate)
    #app.start()
    def toggleLED():
        while 1:
            mText = '{"task": "/ledarr_act", "led": {"LEDArrMode": 1, "led_array": [{"id": 0, "r": 22, "g": 45, "b": 29}]}, "qid": 1}' 
            app.send_text(mText)
            time.sleep(1)
            mText = '{"task": "/ledarr_act", "led": {"LEDArrMode": 0, "led_array": [{"id": 0, "r": 22, "g": 45, "b": 29}, {"id": 1, "r": 12, "g": 34, "b": 22}, {"id": 2, "r": 34, "g": 11, "b": 50}, {"id": 3, "r": 32, "g": 22, "b": 2}, {"id": 4, "r": 37, "g": 1, "b": 35}, {"id": 5, "r": 21, "g": 10, "b": 28}, {"id": 6, "r": 52, "g": 16, "b": 5}, {"id": 7, "r": 2, "g": 43, "b": 29}, {"id": 8, "r": 42, "g": 2, "b": 39}, {"id": 9, "r": 21, "g": 21, "b": 22}, {"id": 10, "r": 44, "g": 28, "b": 35}, {"id": 11, "r": 31, "g": 40, "b": 52}, {"id": 12, "r": 25, "g": 45, "b": 15}, {"id": 13, "r": 20, "g": 24, "b": 1}, {"id": 14, "r": 49, "g": 48, "b": 37}, {"id": 15, "r": 54, "g": 3, "b": 41}, {"id": 16, "r": 14, "g": 17, "b": 16}, {"id": 17, "r": 48, "g": 31, "b": 47}, {"id": 18, "r": 43, "g": 24, "b": 10}, {"id": 19, "r": 23, "g": 28, "b": 54}, {"id": 20, "r": 42, "g": 54, "b": 38}, {"id": 21, "r": 32, "g": 51, "b": 4}, {"id": 22, "r": 31, "g": 38, "b": 5}, {"id": 23, "r": 41, "g": 0, "b": 8}, {"id": 24, "r": 26, "g": 6, "b": 44}, {"id": 25, "r": 41, "g": 30, "b": 0}, {"id": 26, "r": 48, "g": 13, "b": 14}, {"id": 27, "r": 48, "g": 52, "b": 24}, {"id": 28, "r": 18, "g": 6, "b": 28}, {"id": 29, "r": 14, "g": 47, "b": 5}, {"id": 30, "r": 2, "g": 31, "b": 24}, {"id": 31, "r": 53, "g": 8, "b": 50}, {"id": 32, "r": 1, "g": 15, "b": 14}, {"id": 33, "r": 19, "g": 18, "b": 39}, {"id": 34, "r": 44, "g": 22, "b": 29}, {"id": 35, "r": 4, "g": 38, "b": 9}, {"id": 36, "r": 1, "g": 28, "b": 54}, {"id": 37, "r": 37, "g": 43, "b": 22}, {"id": 38, "r": 14, "g": 27, "b": 27}, {"id": 39, "r": 22, "g": 10, "b": 49}, {"id": 40, "r": 32, "g": 29, "b": 39}, {"id": 41, "r": 14, "g": 2, "b": 41}, {"id": 42, "r": 39, "g": 37, "b": 35}, {"id": 43, "r": 26, "g": 44, "b": 32}, {"id": 44, "r": 45, "g": 19, "b": 53}, {"id": 45, "r": 44, "g": 26, "b": 37}, {"id": 46, "r": 40, "g": 28, "b": 11}, {"id": 47, "r": 9, "g": 4, "b": 23}, {"id": 48, "r": 41, "g": 22, "b": 31}, {"id": 49, "r": 10, "g": 5, "b": 46}, {"id": 50, "r": 48, "g": 39, "b": 52}, {"id": 51, "r": 33, "g": 15, "b": 26}, {"id": 52, "r": 50, "g": 19, "b": 44}, {"id": 53, "r": 34, "g": 18, "b": 35}, {"id": 54, "r": 6, "g": 0, "b": 39}, {"id": 55, "r": 6, "g": 26, "b": 43}, {"id": 56, "r": 24, "g": 35, "b": 21}, {"id": 57, "r": 47, "g": 8, "b": 31}, {"id": 58, "r": 1, "g": 0, "b": 32}, {"id": 59, "r": 52, "g": 12, "b": 28}, {"id": 60, "r": 39, "g": 53, "b": 5}, {"id": 61, "r": 6, "g": 32, "b": 41}, {"id": 62, "r": 28, "g": 0, "b": 24}, {"id": 63, "r": 34, "g": 46, "b": 27}]}, "qid": 2}'
            app.send_text(mText)
            time.sleep(2)
    import threading
    mThread = threading.Thread(target=toggleLED)
    mThread.start()
    mThread.join()
    
