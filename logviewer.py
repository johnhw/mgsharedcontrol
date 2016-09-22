import sys, os
from Tkinter import *
import socket, cPickle, logging
from datetime import datetime
from threading import Thread
from time import sleep
from Queue import Queue, Empty
import demjson
import config

class LogReceiver(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True # don't keep this thread around if main thread exits
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', config.LOG_PORT))
        self.sock.setblocking(0)
        self.q = Queue()
        self.logfile = open(self.gen_log_name(), 'w')
        self.done = False

    def get_log_name(self):
        return self.logfile.name

    def gen_log_name(self):
        return 'shared_control_%s.log' % (datetime.now().strftime('%Y%m%d_%H%M%S'))

    def run(self):
        while not self.done:
            try:
                data, addr = self.sock.recvfrom(8192)
                # DatagramHandler sends the log data in pickled form with a 4-byte
                # int header at the start giving the packet length
                rec = cPickle.loads(data[4:])

                # add record to the queue and log it to disk as well
                self.q.put(rec)
                self.logfile.write(str(rec) + '\n')
            except socket.error:
                sleep(0.01)

    def get_messages(self):
        """
        Called by LogViewer to retrieve all items in the queue
        """
        messages = []
        while True:
            try:
                msg = self.q.get_nowait()
                messages.append(msg)
            except Empty:
                break

        return messages

    def stop(self):
        self.done = True
        self.sock.close()
        self.logfile.close()

class LogViewer(object):

    DEFAULT_BG = '#f0f0ed'

    def __init__(self):
        self.receiver = LogReceiver()
        self.messages = []
        self.filtered_messages = []

        self.root = Tk()
        self.root.geometry('950x500+50+50')
        self.root.title("Shared control log viewer [%s]" % self.receiver.get_log_name())

        # grid row/col weighting adjustments
        self.root.rowconfigure(index=1, weight=1)
        self.root.rowconfigure(index=8, weight=1)
        self.root.columnconfigure(index=0, weight=1)

        # StringVars for the text widgets that need modified
        self.filter_message = StringVar(self.root, "")
        self.filter_text = StringVar()

        # create all the Tk widgets

        # Label next to the filter textbox
        self.filter_label = Label(self.root, textvariable=self.filter_message, bg=LogViewer.DEFAULT_BG)
        # Filter textbox
        self.filter = Entry(self.root, textvariable=self.filter_text)
        # List of log messages
        self.listbox = Listbox(self.root)
        # Vertical scrollbar for the list
        self.listvscroll = Scrollbar(self.root)
        # Horizontal scrollbar for the list
        self.listhscroll = Scrollbar(self.root, orient=HORIZONTAL)
        # Label for the listbox
        self.logheader = Label(self.root, text="Log messages:", bg=LogViewer.DEFAULT_BG)
        # Text widget to display JSON content
        self.jsontext = Text(self.root, height=6)
        # Label for the JSON text widget
        self.jsonheader = Label(self.root, text="JSON:", bg=LogViewer.DEFAULT_BG)

        # place all the widgets using the grid layout manager

        self.logheader.grid(row=0, column=0, sticky=W)
        self.listbox.grid(row=1, column=0, rowspan=4, columnspan=4, padx=5, pady=5, sticky=NSEW)
        self.listvscroll.grid(row=1, column=4, rowspan=4, sticky=NS)
        self.listhscroll.grid(row=5, column=0, columnspan=4, sticky=EW)

        self.filter_label.grid(row=6, column=0, sticky=E)
        self.filter.grid(row=6, column=1, sticky=W)

        self.jsonheader.grid(row=7, column=0, sticky=W)
        self.jsontext.grid(row=8, column=0, columnspan=4, padx=5, pady=5, sticky=NSEW)

        # set up event handling/states

        # call filter_updated whenever the filter_text value is modified
        self.filter_text.trace("w", self.filter_updated)
        # link scrollbars to listbox
        self.listbox.config(yscrollcommand=self.listvscroll.set)
        self.listvscroll.config(command=self.listbox.yview)
        self.listbox.config(xscrollcommand=self.listhscroll.set)
        self.listhscroll.config(command=self.listbox.xview)
        # handle selections in the listbox
        self.listbox.bind('<<ListboxSelect>>', self.selected_message)
        # make the text widget for displaying JSON content read only
        self.jsontext.config(state=DISABLED)
        # set main window background colour
        self.root.configure(background=LogViewer.DEFAULT_BG)
        # handlers for pressing escape or closing the window 
        self.root.bind('<Escape>', lambda x: self.quit())
        self.root.protocol('WM_DELETE_WINDOW', self.quit)

        # set update to be called every 50ms to retrieve newly received messages
        self.root.after(50, self.update)

        self.receiver.start()

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()

    def quit(self):
        self.receiver.stop()
        sys.exit(0)

    def format_rec(self, rec):
        """
        Formats a log record object for display in the listbox
        """
        dt = datetime.fromtimestamp(rec['created'])
        return '[%s.%d][%s/%s.%s] %s' % (dt.strftime('%H:%M:%S'), dt.microsecond/1000, rec['levelname'], rec['module'], rec['funcName'], rec['msg'])

    def selected_message(self, event):
        """
        Handler for clicks on items in the listbox
        """
        w = event.widget

        # get selected item index
        if len(w.curselection()) == 0:
            return
        index = int(w.curselection()[0])

        # get the content of the selected index
        val = w.get(index)

        # delete current content of the JSON text widget
        self.jsontext.config(state=NORMAL)
        self.jsontext.delete('0.0', END)

        # if it looks like the value contains JSON
        if val.find("{") != -1:
            try:
                # decode the JSON content (demjson is less strict than the json module)
                msg = demjson.decode(val[val.find("{"):])

                # do some (very) basic pretty printing
                pp = '{\n'
                keys = msg.keys()
                keys.sort()
                for k in keys:
                    pp += '    %s : "%s",\n' % (k, msg[k])
                pp = pp[:-2] + '\n}'
                self.jsontext.insert('0.0', pp)
            except Exception, e:
                self.jsontext.insert('0.0', 'Not JSON/error parsing content %s' % e)

        # make the widget read-only again
        self.jsontext.config(state=DISABLED)

    def get_filter_message(self):
        """
        Returns the label text for the filter text box 
        """
        return 'Filter messages [%d/%d]:' % (self.listbox.size(), len(self.messages))

    def record_matches(self, rec, filt):
        """
        Returns True if the text <filt> appears in any of the selected fields in <rec>
        """
        for f in ['name', 'pathname', 'filename', 'funcName', 'levelname', 'msg']:
            if rec[f].find(filt) != -1:
                return True

        return False

    def filter_updated(self, name, index, mode):
        """
        Handler for the user typing in the filter text widget. Updates the content
        of the listbox based on the new filter text.
        """
        # retrieve current text and delete all listbox content
        filt = self.filter_text.get()
        self.listbox.delete(0, END)

        # find all messages matching the current filter text
        fm = []
        for m in self.messages:
            if len(filt) == 0 or self.record_matches(m, filt):
                fm.append(m)
                self.listbox.insert(0, self.format_rec(m))

        self.filtered_messages = fm
        self.filter_message.set(self.get_filter_message())

    def update(self):
        """
        Called every 50ms using after() to retrieve newly received messages from
        the LogReceiver instance. Adds any messages matching the current filter
        to the listbox and appends all of them to the overall list.
        """
        new_messages = self.receiver.get_messages()
        if len(new_messages) > 0:
            filt = self.filter_text.get()
            for n in new_messages:
                if len(filt) == 0 or self.record_matches(n, filt):
                    self.listbox.insert(0, self.format_rec(n))
                    self.filtered_messages.append(n)
            self.messages.extend(new_messages)

        self.filter_message.set(self.get_filter_message())
        self.root.after(50, self.update)

if __name__ == "__main__":
    LogViewer()
