#!/usr/bin/env python3

import logging
import os
import shutil
import threading
from typing import Any, Dict, List, Optional

import yaml
from google.cloud.firestore_v1 import DocumentReference, DocumentSnapshot
from google.cloud.firestore_v1.watch import ChangeType, DocumentChange
from proto.datetime_helpers import DatetimeWithNanoseconds

from firestore_client_handler import FirestoreClientHandler

logger = logging.getLogger(__name__)


class InvalidLocalService(Exception):
    """Local service is invalid."""


class InvalidRemoteService(Exception):
    """Remote service is invalid."""


class InstalledServicesDownloader(FirestoreClientHandler):
    """Service that handles the installed services of the service and updates the local iombian services accordingly.

    To start the service call `read_local_services()` and then `start()`.
    """

    RESTART_DELAY_TIME_S = 0.5

    user_id: str
    """Id of the owner of the device."""
    device_id: str
    """Id of the device."""
    device: Optional[DocumentReference]
    """Reference to the firestore document of this device."""
    services: List[str]
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
    ):
        super().__init__(api_key, project_id, refresh_token)
        self.device_id = device_id
        self.device = None
        self.services = []
        self.base_path = base_path

    def _get_local_version(self, service_name: str) -> str:
        """Get the version of the local service given the service name.
        The local service is the one installed on the IoMBan device.
        """
        logger.debug(f"Getting local version for '{service_name}' service")
        compose_path = f"{self.base_path}/{service_name}/docker-compose.yaml"
        try:
            with open(compose_path, "r") as docker_compose_txt:
                docker_compose = yaml.safe_load(docker_compose_txt)

            local_version = docker_compose["services"][service_name]["labels"][
                f"com.{service_name}.service.version"
            ]
            return local_version
        except:
            logger.warning(f"Invalid local service {service_name}")
            raise InvalidLocalService

    def _get_remote_version(self, service_snapshot: DocumentSnapshot) -> str:
        """Get the version of the remote service given the services `DocumentSnapshot`.
        The remote service is the one in firebase.
        """
        logger.debug("Getting remote version for the service")
        service_dict = service_snapshot.to_dict()
        if service_dict is None:
            logger.warning(f"Invalid remote service {service_snapshot.id}")
            raise InvalidRemoteService

        version = service_dict.get("version")
        if version is None:
            logger.warning(f"Invalid remote service: '{service_snapshot.id}'")
            raise InvalidRemoteService

        return version

    def _get_local_envs(self, service_name: str):
        """Get the environment variables of the local service given the service name.
        The local service is the one installed on the iombian.

        If the local service or env is not found or the envs don't follow the given structure raise a `InvalidLocalService` error.
        """
        logger.debug(f"Getting local env vars for '{service_name}' service")
        envs: Dict[str, Any] = {}
        env_path = f"{self.base_path}/{service_name}/.env"
        try:
            with open(env_path, "r") as env_txt:
                lines = env_txt.readlines()

            for line in lines:
                if "\n" in line:
                    line = line[:-1]
                key, value = line.split("=")
                envs[key] = value
            return envs
        except:
            logger.warning(f"Invalid local service: '{service_name}'")
            raise InvalidLocalService

    def _get_remote_envs(self, service_snapshot: DocumentSnapshot) -> Dict[str, Any]:
        """Get the environment variables of the remote service given the services `DocumentSnapshot`.
        The remote service is the one installed in firebase.

        If the remote service has no fields or the fields don't have a env field raise a `InvalidRemoteService` error.
        """
        logger.debug("Getting remote env vars for the service")
        service_dict = service_snapshot.to_dict()
        if service_dict is None:
            logger.warning(f"Invalid remote serivce {service_snapshot.id}")
            raise InvalidRemoteService

        envs = service_dict.get("envs")
        if envs is None:
            logger.warning(f"Invalid remote serivce {service_snapshot.id}")
            raise InvalidRemoteService

        return envs

    def _get_remote_compose(
        self, service_name: str, service_snapshot: DocumentSnapshot
    ) -> Optional[Dict[str, Any]]:
        """Get the docker compose of the remote service given the service name and `DocumentSnapshot`.
        The remote service is the one installed in firebase.
        """
        logger.debug(
            f"Getting remote compose file for '{service_name}' service")
        try:
            version = self._get_remote_version(service_snapshot)
        except InvalidRemoteService:
            return None

        service_dict = (
            self.client.collection("services")
            .document(service_name)
            .collection("versions")
            .document(version)
            .get()
            .to_dict()
        )
        if service_dict is None:
            return None

        return service_dict.get("compose")

    def read_local_services(self):
        """Read the local services and compare them with the ones in firebase.

        Read all the services on the `base_path`.
        For each service, if the service is on firebase, compare the services.
        Depending on the result of the comparison update the service or do nothing.
        If the service is not in firebase, this mean that it was installed manually, so the information should be uploaded.

        If the service in firebase is not valid remove the service from the iombian.
        If the service in the iombian is not valid update the service.
        """
        logger.debug("Checking local and remote services")
        self.services = os.listdir(self.base_path)
        for service_name in self.services:
            logger.debug(f"Checking the {service_name} service")
            service_snapshot = None
            if self.device:
                service_reference = self.device.collection(
                    "installed_services"
                ).document(service_name)
                service_snapshot = service_reference.get()

            if service_snapshot and service_snapshot.exists:
                try:
                    if not self.compare(service_name, service_snapshot):
                        self.remove_local_service(service_name)
                        self.install_local_service(
                            service_name, service_snapshot)
                    else:
                        logger.debug(f"Service {service_name} is up to date")
                except InvalidRemoteService:
                    self.remove_local_service(service_name)
                    self.services.remove(service_name)
                except InvalidLocalService:
                    self.remove_local_service(service_name)
                    try:
                        self.install_local_service(
                            service_name, service_snapshot)
                    except:
                        self.services.remove(service_name)

            else:
                logger.warning(
                    f"'{service_name}' service not available in the remote server")
                self.upload_remote_service(service_name)
        logger.debug(f"Initial local and remote checking done")

    def start(self):
        """Start the Installed Services Downloader by initializing the client and waiting until the connection is ready."""
        logger.debug("Installed Services Downloader started.")
        self.initialize_client()

    def stop(self):
        """Stop the downloader by stopping the listener and the firestore connection."""
        logger.debug("Installed Services Downloader stopped.")
        if self.watch is not None:
            self.watch.unsubscribe()
        self.device = None
        self.stop_client()

    def restart(self):
        """Restart the Installed Services Downloader by calling `stop()` and `start()`."""
        self.stop()
        self.start()

    def remove_local_service(self, service_name: str):
        """Given the service name, remove the service from the IoMBian device."""
        logger.debug(f"Removing '{service_name}' service locally")
        service_path = f"{self.base_path}/{service_name}"
        try:
            shutil.rmtree(service_path)
        except:
            logger.debug(f"Service {service_name} was already removed locally")
        logger.info(f"'{service_name}' service has been locally removed")

    def install_local_service(self, service_name: str, service_snapshot: DocumentSnapshot):
        """Given the service name and `DocumentSnapshot`, install the service from firebase."""
        logger.debug(f"Installing '{service_name}' service locally")
        compose = self._get_remote_compose(service_name, service_snapshot)
        envs_dict = self._get_remote_envs(service_snapshot)

        service_path = f"{self.base_path}/{service_name}"
        try:
            os.mkdir(service_path)
        except FileExistsError:
            pass

        with open(
            f"{self.base_path}/{service_name}/docker-compose.yaml", "w"
        ) as compose_file:
            yaml.dump(compose, compose_file)

        envs_list = [f"{key}={envs_dict[key]}\n" for key in envs_dict]
        with open(f"{self.base_path}/{service_name}/.env", "w") as env_file:
            env_file.writelines(envs_list)
        logger.info(f"'{service_name}' service has been locally installed")

        self.update_remote_service_status(service_name, "downloaded")

    def upload_remote_service(self, service_name: str):
        """Given the service name, upload the local service info to firebase."""
        logger.debug(f"Uploading '{service_name}' service info to Firebase")

        local_service_version = self._get_local_version(service_name)
        local_service_envs = self._get_local_envs(service_name)

        service_reference = self.device.collection("installed_services").document(
            service_name
        )
        service_reference.set(
            {"version": local_service_version,
                "envs": local_service_envs,
                "status": "downloaded"}
        )
        logger.info(f"'{service_name}' service info uploaded to Firebase")

    def remove_remote_service(self, service_name: str):
        """Given the service name, remove the service from firebase."""
        logger.debug(f"Removing '{service_name}' service from Firebase")
        service_reference = self.device.collection("installed_services").document(
            service_name
        )
        service_reference.delete()

    def update_remote_service_status(self, service_name: str, service_status: str):
        """Given the service name and a status, update the service status in firebase."""
        logger.debug(
            f"Updating '{service_name}' service status to {service_status} in Firebase")
        service_reference = self.device.collection("installed_services").document(
            service_name
        )
        service_reference.update({"status": service_status})

    def is_remote_service_status_X(self, service_snapshot: DocumentSnapshot, status: str):
        """Return `True` if the remote service status is X (the 'status' parameter)."""
        service_dict = service_snapshot.to_dict()
        service_status = service_dict.get("status")
        if not service_status:
            return False
        return service_status == status

    def compare(self, service_name: str, service_snapshot: DocumentSnapshot):
        """Return `True` if local and remote services are the same. If not return `False`."""
        try:
            remote_version = self._get_remote_version(service_snapshot)
            local_version = self._get_local_version(service_name)

            if local_version != remote_version:
                return False

            remote_envs = self._get_remote_envs(service_snapshot)
            local_envs = self._get_local_envs(service_name)

            return local_envs == remote_envs
        except (InvalidLocalService, InvalidRemoteService) as error:
            logger.error(f"Invalid local or remote service: {error}")
            return False

    def on_client_initialized(self):
        """Callback function when the client is initialized."""
        logger.debug("Firestore client initialized")
        self.device = (
            self.client.collection("users")
            .document(self.user_id)
            .collection("devices")
            .document(self.device_id)
        )
        self.read_local_services()
        self.watch = self.device.collection("installed_services").on_snapshot(
            self._on_installed_service_change
        )

    def on_server_not_responding(self):
        """Callback function when the server is not responding."""
        logger.error("Firestore server not responding")
        threading.Timer(self.RESTART_DELAY_TIME_S, self.restart).start()

    def on_token_expired(self):
        """Callback function when the token is expired."""
        logger.debug("Refreshing Firebase client token id")
        threading.Timer(self.RESTART_DELAY_TIME_S, self.restart).start()

    def _on_installed_service_change(
        self,
        snapshots: List[DocumentSnapshot],
        changes: List[DocumentChange],
        read_time: DatetimeWithNanoseconds,
    ):
        """For each change in the installed services collection, check the service status and react
        accordingly.

        Here is the list of the status values that should be handled:
            - to-be-installed: the user has indicated that the service should be installed.
            - to-be-updated: the user has changed the configuratior of the service (env vars)
            - to-be-removed: the service is ready to be removed from Firebase.
        """
        for change in changes:
            service_snapshot = change.document
            service_name = service_snapshot.id

            if change.type == ChangeType.REMOVED:
                continue

            logger.debug(
                f"Firebase notification received for {service_name} service")
            if self.is_remote_service_status_X(service_snapshot, "to-be-installed"):
                if service_name in self.services:
                    self.update_remote_service_status(
                        service_name, "downloaded")
                    continue
                try:
                    self.install_local_service(service_name, service_snapshot)
                    self.services.append(service_name)
                except InvalidRemoteService:
                    pass

            elif self.is_remote_service_status_X(service_snapshot, "to-be-updated"):
                self.install_local_service(service_name, service_snapshot)
                if service_name not in self.services:
                    self.services.append(service_name)

            elif self.is_remote_service_status_X(service_snapshot, "to-be-removed"):
                self.remove_local_service(service_name)
                if service_name in self.services:
                    self.services.remove(service_name)
                self.remove_remote_service(service_name)

            else:
                if self.compare(service_name, service_snapshot):
                    logger.debug(
                        f"Local and remote services are the same for '{service_name}'")
                    continue
                self.remove_local_service(service_name)
                try:
                    self.install_local_service(service_name, service_snapshot)
                    if service_name not in self.services:
                        self.services.append(service_name)
                except InvalidRemoteService:
                    if service_name in self.services:
                        self.services.remove(service_name)
