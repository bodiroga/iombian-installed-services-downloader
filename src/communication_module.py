#!/usr/bin/env python3

import logging
import zmq

logger = logging.getLogger(__name__)


class CommunicationModule(object):

    def __init__(self, host="127.0.0.1", port=5555):
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)

    def start(self):
        logger.debug(f"Starting communication module ('{self.host}:{self.port}')")
        self.socket.connect(f"tcp://{self.host}:{self.port}")

    def stop(self):
        logger.debug("Stopping communication module")
        self.socket.close()
        self.context.term()

    def execute_command(self, command, params=None):
        if not command:
            logger.error("The command argument is required")
            return
        self.socket.send_json({ "command": command, "params": params})
        response = self.socket.recv_json()
        return response