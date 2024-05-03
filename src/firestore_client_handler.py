#!/usr/bin/env python3

from google.cloud.firestore import Client
from google.cloud.firestore_v1 import watch
from google.oauth2.credentials import Credentials
import google.api_core
import json
import logging
import requests
import threading
import time

logger = logging.getLogger(__name__)

watch._should_recover = lambda _: False
watch._should_terminate = lambda _: True


class FirestoreClientHandler:

    REFRESH_TOKEN_TIME_MIN = 58
    INITIALIZATION_RETRY_TIME_MIN = 1
    SERVER_RESPONSE_TIMEOUT_S = 60

    def __init__(self, api_key: str, project_id: str, refresh_token: str):
        self.api_key = api_key
        self.project_id = project_id
        self.refresh_token = refresh_token
        self.token_expired_timer = None
        self.initialization_retry_timer = None
        self.server_responde_message_handler = None
        self.user_id = None
        self.client = None

    def initialize_client(self, notify=True):
        if self.client:
            if notify:
                threading.Thread(
                    target=self.on_client_initialized, daemon=True).start()
            return

        logger.debug("Initializing Firestore client")
        creds = self._get_credentials()

        if not creds:
            if self.initialization_retry_timer:
                return
            self.initialization_retry_timer = threading.Timer(
                self.INITIALIZATION_RETRY_TIME_MIN*60.0, self.on_initialization_retry)
            self.initialization_retry_timer.start()
            return

        self.client = Client(self.project_id, creds)
        logger.debug("Firebase client initialized")
        if notify:
            threading.Thread(target=self.on_client_initialized,
                             daemon=True).start()
        self.server_responde_message_handler = ServerResponseMessageHandler(
            timeout_s=self.SERVER_RESPONSE_TIMEOUT_S, on_server_not_responding=self.on_server_not_responding)
        google.api_core.bidi._LOGGER = BidiCustomLogger()
        google.api_core.bidi._LOGGER.addHandler(
            self.server_responde_message_handler)
        self.token_expired_timer = threading.Timer(
            self.REFRESH_TOKEN_TIME_MIN*60.0, self.on_token_expired)
        self.token_expired_timer.start()

    def stop_client(self):
        logger.debug("Stopping Firestore client")
        self.client = None
        if self.server_responde_message_handler:
            self.server_responde_message_handler.stop()
            self.server_responde_message_handler = None
        if self.initialization_retry_timer:
            self.initialization_retry_timer.cancel()
            self.initialization_retry_timer.join()
            self.initialization_retry_timer = None
        if self.token_expired_timer:
            self.token_expired_timer.cancel()
            self.token_expired_timer.join()
            self.token_expired_timer = None

    def on_client_initialized(self):
        logger.warning(
            "This function should be overwritten by the child class")

    def on_server_not_responding(self):
        logger.warning(
            "This function should be overwritten by the child class")

    def on_token_expired(self):
        logger.warning(
            "This function should be overwritten by the child class")

    def on_initialization_retry(self):
        logger.warning("Retrying firebase client initialization...")
        self.initialization_retry_timer = None
        threading.Thread(target=self.initialize_client).start()

    def _get_credentials(self):
        user_id, token_id = self._get_ids()
        if not user_id or not token_id:
            logger.debug(f"Invalid user and token ids ({user_id}, {token_id})")
            return None
        self.user_id = user_id
        creds = Credentials(token_id, self.refresh_token)
        return creds

    def _get_ids(self):
        token_response = self._get_token_response()
        user_id = token_response.get("user_id")
        token_id = token_response.get("id_token")
        return (user_id, token_id)

    def _get_token_response(self):
        request_ref = f"https://securetoken.googleapis.com/v1/token?key={self.api_key}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"grantType": "refresh_token",
                          "refreshToken": self.refresh_token})
        try:
            response_object = requests.post(
                request_ref, headers=headers, data=data)
            return response_object.json()
        except Exception as e:
            return {}


class BidiCustomLogger(logging.Logger):

    def __init__(self, name="google.api_core.bidi", level=logging.DEBUG):
        super().__init__(name, level)


class ServerResponseMessageHandler(logging.StreamHandler):

    def __init__(self, timeout_s=60, on_server_not_responding=lambda _: None, server_response_msg="recved response.", watchdog_timeout_msg="watchdog timeout"):
        super().__init__()
        self.timeout_s = timeout_s
        self.on_server_not_responding = on_server_not_responding
        self.server_response_msg = server_response_msg
        self.server_response_last_time = time.time()
        self.watchdog_timeout_msg = watchdog_timeout_msg
        self.not_responding_timer = None
        self.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)-8s - %(name)-16s - %(message)s', None, '%'))

    def emit(self, record):
        msg = self.format(record)
        if self.watchdog_timeout_msg in msg:
            logger.debug("Server connection timeout detected")
            threading.Thread(target=self.on_server_not_responding).start()
        if self.server_response_msg in msg:
            logger.debug("Server response message caught ({} seconds)".format(
                time.time() - self.server_response_last_time))
            self.server_response_last_time = time.time()
            if self.not_responding_timer:
                self.stop()
            self.not_responding_timer = threading.Timer(
                self.timeout_s, self.on_server_not_responding)
            self.not_responding_timer.start()
        if record.levelno >= logger.getEffectiveLevel():
            super().emit(record)

    def stop(self):
        if self.not_responding_timer:
            self.not_responding_timer.cancel()
            self.not_responding_timer.join()
            self.not_responding_timer = None
