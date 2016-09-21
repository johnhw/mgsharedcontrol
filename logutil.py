import logging
from logging.handlers import DatagramHandler
import config

def get_logger(name):
    logger = logging.getLogger(name)
    logger.propagate = config.LOG_TO_STDOUT
    logger.setLevel(config.LOG_LEVEL)
    logger.addHandler(DatagramHandler(config.LOG_IP, config.LOG_PORT))
    return logger
