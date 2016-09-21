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
        self.daemon = True
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
                rec = cPickle.loads(data[4:])
                self.q.put(rec)
                self.logfile.write(str(rec) + '\n')
            except socket.error:
                sleep(0.01)

    def get_messages(self):
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
        self.root = Tk()
        self.root.geometry('950x500+50+50')
        self.root.title("Shared control log viewer [%s]" % self.receiver.get_log_name())

        self.root.rowconfigure(index=1, weight=1)
        self.root.rowconfigure(index=8, weight=1)
        self.root.columnconfigure(index=0, weight=1)

        self.filter_message = StringVar(self.root, "")
        self.filter_text = StringVar()

        self.filter_label = Label(self.root, textvariable=self.filter_message, bg=LogViewer.DEFAULT_BG)
        self.filter = Entry(self.root, textvariable=self.filter_text)
        self.listbox = Listbox(self.root)
        self.listvscroll = Scrollbar(self.root)
        self.listhscroll = Scrollbar(self.root, orient=HORIZONTAL)
        self.jsontext = Text(self.root, height=6)
        self.jsonheader = Label(self.root, text="JSON:", bg=LogViewer.DEFAULT_BG)
        self.logheader = Label(self.root, text="Log messages:", bg=LogViewer.DEFAULT_BG)

        self.logheader.grid(row=0, column=0, sticky=W)
        self.listbox.grid(row=1, column=0, rowspan=4, columnspan=4, padx=5, pady=5, sticky=NSEW)
        self.listvscroll.grid(row=1, column=4, rowspan=4, sticky=NS)
        self.listhscroll.grid(row=5, column=0, columnspan=4, sticky=EW)

        self.filter_label.grid(row=6, column=0, sticky=E)
        self.filter.grid(row=6, column=1, sticky=W)

        self.jsonheader.grid(row=7, column=0, sticky=W)
        self.jsontext.grid(row=8, column=0, columnspan=4, padx=5, pady=5, sticky=NSEW)

        self.filter_text.trace("w", self.filter_updated)
        self.listbox.config(yscrollcommand=self.listvscroll.set)
        self.listvscroll.config(command=self.listbox.yview)
        self.listbox.config(xscrollcommand=self.listhscroll.set)
        self.listhscroll.config(command=self.listbox.xview)
        self.listbox.bind('<<ListboxSelect>>', self.selected_message)
        self.jsontext.config(state=DISABLED)

        self.root.configure(background=LogViewer.DEFAULT_BG)

        self.root.after(50, self.update)

        self.receiver.start()

        self.root.bind('<Escape>', lambda x: self.root.destroy())
        self.root.protocol('WM_DELETE_WINDOW', self.root.destroy)

        self.messages = []
        self.filtered_messages = []

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.receiver.stop()
            sys.exit(-1)

    def quit(self):
        self.receiver.stop()
        sys.exit(0)

    def format_rec(self, rec):
        dt = datetime.fromtimestamp(rec['created'])
        return '[%s][%s/%s][%s.%s] %s' % (dt.strftime('%H:%M:%S'), rec['name'], rec['levelname'], rec['module'], rec['funcName'], rec['msg'])

    def selected_message(self, event):
        w = event.widget
        if len(w.curselection()) == 0:
            return
        index = int(w.curselection()[0])
        val = w.get(index)
        self.jsontext.config(state=NORMAL)
        self.jsontext.delete('0.0', END)
        if val.find("{") != -1:
            try:
                msg = demjson.decode(val[val.find("{"):])
                # (very) basic pretty printing
                pp = '{\n'
                keys = msg.keys()
                keys.sort()
                for k in keys:
                    pp += '    %s : "%s",\n' % (k, msg[k])
                pp = pp[:-2] + '\n}'
                self.jsontext.insert('0.0', pp)
            except Exception, e:
                self.jsontext.insert('0.0', 'Not JSON/error parsing content %s' % e)

        self.jsontext.config(state=DISABLED)

    def get_filter_message(self):
        return 'Filter messages [%d/%d]:' % (self.listbox.size(), len(self.messages))

    def record_matches(self, rec, filt):
        for f in ['name', 'pathname', 'filename', 'funcName', 'levelname', 'msg']:
            if rec[f].find(filt) != -1:
                return True

        return False

    def filter_updated(self, name, index, mode):
        fm = []
        filt = self.filter_text.get()
        self.listbox.delete(0, END)

        for m in self.messages:
            if len(filt) == 0 or self.record_matches(m, filt):
                fm.append(m)
                self.listbox.insert(0, self.format_rec(m))

        self.filter_message.set(self.get_filter_message())
        self.filtered_messages = fm

    def update(self):
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
