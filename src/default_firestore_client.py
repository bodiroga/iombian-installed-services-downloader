import logging
import threading

from firestore_client_handler import FirestoreClientHandler

logger = logging.getLogger(__name__)


class DefaultFirestoreClient(FirestoreClientHandler):
    RESTART_DELAY_TIME_S = 0.5

    def restart(self):
        logger.debug("Restarting Firestore Parameters Handler")
        self.stop_client()
        self.initialize_client()

    def on_client_initialized(self):
        logger.info("Firestore client initialized")

    def on_server_not_responding(self):
        logger.error("Firestore server not responding")
        threading.Timer(self.RESTART_DELAY_TIME_S, self.restart).start()

    def on_token_expired(self):
        logger.debug("Refreshing Firebase client token id")
        threading.Timer(self.RESTART_DELAY_TIME_S, self.restart).start()
