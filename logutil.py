import socket
import logging
from logging.handlers import DatagramHandler
import config

class DatagramHandler2(DatagramHandler):
    """
    Simple subclassing of DatagramHandler to avoid sendto() throwing errors
    when there's nothing listening for packets
    """
    def __init__(self, host, port):
        DatagramHandler.__init__(self, host, port)

    def send(self, s):
        if self.sock is None:
            self.createSocket()

        try:
            self.sock.sendto(s, (self.host, self.port))
        except socket.error:
            pass

def get_logger(name):
    logger = logging.getLogger(name)
    logger.propagate = config.LOG_TO_STDOUT
    logger.setLevel(config.LOG_LEVEL)
    logger.addHandler(DatagramHandler2(config.LOG_IP, config.LOG_PORT))
    return logger
