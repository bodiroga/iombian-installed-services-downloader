#!/usr/bin/env python3

import logging
import os
import threading
from typing import Set, List, Optional

from google.cloud.firestore import DocumentReference, DocumentSnapshot
from google.cloud.firestore_v1.watch import ChangeType, DocumentChange
from proto.datetime_helpers import DatetimeWithNanoseconds

from firestore_client_handler import FirestoreClientHandler
from installed_service import InstalledService, InstallationFailed, ReconfigurationFailed, UpdateFailed
from installed_remote_service import InstalledRemoteService
from installed_local_service import InstalledLocalService

logger = logging.getLogger(__name__)


class InstalledServicesDownloader(FirestoreClientHandler):
    """Service that handles the installed services of the service and updates the local iombian services accordingly.

    To start the service call `start()`.
    """

    RESTART_DELAY_TIME_S = 0.5

    user_id: str
    """Id of the owner of the device."""
    device_id: str
    """Id of the device."""
    device: Optional[DocumentReference]
    """Reference to the firestore document of this device."""
    services: Set[str]
    """The services in the local iombian."""
    base_path: str
    """The base path where the services are installed (normally "/opt/iombian-services")."""


    def __init__(
        self,
        api_key: str,
        project_id: str,
        refresh_token: str,
        device_id: str,
        base_path: str,
    ) -> None:
        super().__init__(api_key, project_id, refresh_token)
        self.device_id = device_id
        self.device = None
        self.services = set()
        self.base_path = base_path
        self.subscription = None

    def _check_local_services(self) -> None:
        """Read all the services on the `base_path` and process them individually."""
        logger.debug("Checking all local services")
        self.services = set(os.listdir(self.base_path))
        for service_name in self.services:
            self._check_local_service(service_name)
        logger.debug(f"Initial local and remote checking done")

    def _check_local_service(self, service_name: str) -> None:
        """Process the local service given the service name.
        
        For each service, if the service is in firebase, compare the services.
        If the services are different, this means that the the device has been offline for some time.
        If the service is not in firebase, this means that it was installed manually, so the information should be uploaded.
        """
        logger.debug(f"Processing '{service_name}' service")
        service_snapshot: DocumentSnapshot = self.device.collection("installed_services").document(service_name).get()
        installed_remote_service = InstalledRemoteService(service_name, self.device, self.client, service_snapshot)
        installed_local_service = InstalledLocalService(service_name, self.base_path)
        installed_service = InstalledService(service_name, installed_local_service, installed_remote_service)

        if not service_snapshot or not service_snapshot.exists:
            logger.warning(f"Service '{service_name}' not found in Firebase")
            installed_service.upload_service()
            return
        
        if not installed_service.are_services_equal():
            logger.warning(f"Local and remote services are different for '{service_name}'. This must have happened because the device has been offline for some time.")
            return

    def start(self)  -> None:
        """Start the Installed Services Downloader by initializing the client and waiting until the connection is ready."""
        logger.debug("Installed Services Downloader started.")
        self.initialize_client()

    def stop(self) -> None:
        """Stop the downloader by stopping the listener and the firestore connection."""
        logger.debug("Installed Services Downloader stopped.")
        if self.subscription is not None:
            self.subscription.unsubscribe()
        self.device = None
        self.stop_client()

    def restart(self) -> None:
        """Restart the Installed Services Downloader by calling `stop()` and `start()`."""
        self.stop()
        self.start()

    def on_client_initialized(self) -> None:
        """Callback function when the client is initialized."""
        logger.debug("Firestore client initialized")
        self.device = (
            self.client.collection("users")
            .document(self.user_id)
            .collection("devices")
            .document(self.device_id)
        )
        self._check_local_services()
        self.subscription = self.device.collection("installed_services").on_snapshot(
            self._on_installed_service_change
        )

    def on_server_not_responding(self) -> None:
        """Callback function when the server is not responding."""
        logger.error("Firestore server not responding")
        threading.Timer(self.RESTART_DELAY_TIME_S, self.restart).start()

    def on_token_expired(self)-> None:
        """Callback function when the token is expired."""
        logger.debug("Refreshing Firebase client token id")
        threading.Timer(self.RESTART_DELAY_TIME_S, self.restart).start()

    def _on_installed_service_change(
        self,
        _: List[DocumentSnapshot],
        changes: List[DocumentChange],
        __: DatetimeWithNanoseconds,
    ) -> None:
        """For each change in the installed services collection, check the service status and react accordingly.

        Here is the list of the status values that should be handled:
            - to-be-installed: the user has requested that the service should be installed.
            - to-be-reconfigured: the user has changed the configuration of the service (env vars).
            - to-be-updated: the user has requested that the service version should be updated.
            - to-be-removed: the service is ready to be removed from Firebase.
        """
        for change in changes:
            service_snapshot = change.document
            service_name = service_snapshot.id
            installed_remote_service = InstalledRemoteService(service_name, self.device, self.client, service_snapshot)
            installed_local_service = InstalledLocalService(service_name, self.base_path)
            service_status = installed_remote_service.get_status()
            installed_service = InstalledService(service_name, installed_local_service, installed_remote_service)

            if change.type == ChangeType.REMOVED:
                continue

            logger.debug(f"Firebase notification received for '{service_name}' service ({service_status})")

            if service_status == "to-be-installed":
                if service_name in self.services:
                    installed_remote_service.update_service_status("ready")
                    continue
                try:
                    installed_service.install_service()
                    self.services.add(service_name)
                except (InstallationFailed):
                    logger.error(f"'{service_name}' service installation failed ('to-be-installed')")

            elif service_status == "to-be-reconfigured":
                try:
                    installed_service.reconfigure_service()
                except (ReconfigurationFailed):
                    logger.error(f"'{service_name}' service reconfiguration failed ('to-be-reconfigured')")

            elif service_status == "to-be-updated":
                try:
                    installed_service.update_service()
                except (UpdateFailed):
                    logger.error(f"'{service_name}' service update failed ('to-be-updated')")

            elif service_status == "to-be-removed":
                installed_service.remove_service()
                if service_name in self.services:
                    self.services.remove(service_name)

            elif not installed_service.are_services_equal():
                logger.error(f"Local and remote services are different for '{service_name}', this should not happen")
 