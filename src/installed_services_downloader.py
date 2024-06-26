import logging
import os
import shutil
import threading
from typing import Any, Dict, List, Optional, TypedDict

import yaml
from google.cloud.firestore_v1 import DocumentReference, DocumentSnapshot
from google.cloud.firestore_v1.watch import ChangeType, DocumentChange
from proto.datetime_helpers import DatetimeWithNanoseconds

from firestore_client_handler import FirestoreClientHandler

logger = logging.getLogger(__name__)


class InstalledService(TypedDict):
    """Dict representing the installed_services structure in firebase.

    The structure of the document is `Dict[str, InstalledServices]`.
    """

    version: str
    env: Dict[str, Any]


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
        compose_path = f"{self.base_path}/{service_name}/docker-compose.yaml"
        try:
            with open(compose_path, "r") as docker_compose_txt:
                docker_compose = yaml.safe_load(docker_compose_txt)

            local_version = docker_compose["services"][service_name]["labels"][
                f"com.{service_name}.service.version"
            ]
            return local_version
        except:
            logger.warning(f"Invalid local serivce {service_name}")
            raise InvalidLocalService

    def _get_remote_version(self, service_snapshot: DocumentSnapshot) -> str:
        """Get the version of the remote service given the services `DocumentSnapshot`.
        The remote service is the one in firebase.
        """
        service_dict = service_snapshot.to_dict()
        if service_dict is None:
            logger.warning(f"Invalid remote serivce {service_snapshot.id}")
            raise InvalidRemoteService

        version = service_dict.get("version")
        if version is None:
            logger.warning(f"Invalid remote serivce {service_snapshot.id}")
            raise InvalidRemoteService

        return version

    def _get_local_envs(self, service_name: str):
        """Get the environment variables of the local service given the service name.
        The local service is the one installed on the iombian.

        If the local service or env is not found or the envs don't follow the given structure raise a `InvalidLocalService` error.
        """
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
            logger.warning(f"Invalid remote serivce {service_name}")
            raise InvalidLocalService

    def _get_remote_envs(self, service_snapshot: DocumentSnapshot) -> Dict[str, Any]:
        """Get the environment variables of the remote service given the services `DocumentSnapshot`.
        The remote service is the one installed in firebase.

        If the remote service has no fields or the fields don't have a env field raise a `InvalidRemoteService` error.
        """
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
        If the service is not in firebase, this mean that it was removed while the iombian was off, so remove the service from the iombian.

        If the service in firebase is not valid remove the service from the iombian.
        If the service in the iombian is not valid update the service.
        """
        logger.debug("Syncing local and remote services")
        self.services = os.listdir(self.base_path)
        for service_name in self.services:
            service_snapshot = None
            if self.device:
                service_reference = self.device.collection(
                    "installed_services"
                ).document(service_name)
                service_snapshot = service_reference.get()

            if service_snapshot and service_snapshot.exists:
                try:
                    logger.debug(service_name)
                    logger.debug(service_snapshot)
                    if not self.compare(service_name, service_snapshot):
                        self.remove_service(service_name)
                        self.install_service(service_name, service_snapshot)
                    else:
                        logger.debug(f"Service {service_name} is up to date")
                except InvalidRemoteService:
                    self.remove_service(service_name)
                    self.services.remove(service_name)
                except InvalidLocalService:
                    self.remove_service(service_name)
                    try:
                        self.install_service(service_name, service_snapshot)
                    except:
                        self.services.remove(service_name)

            else:
                self.remove_service(service_name)

    def start(self):
        """Start the Installed Services Downloader by starting the listener, syncing with the remote and starting the firestore connection."""
        logger.info("Installed Services Downloader started.")
        self.initialize_client()
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

    def stop(self):
        """Stop the downloader by stopping the listener and the firestore connection."""
        logger.info("Installed Services Downloader stopped.")
        if self.watch is not None:
            self.watch.unsubscribe()
        self.device = None
        self.stop_client()

    def restart(self):
        """Restart the Installed Services Downloader by calling `stop()` and `start()`."""
        self.stop()
        self.start()

    def remove_service(self, service_name: str):
        """Given the service name, remove the service from the IoMBian device."""
        logger.debug(f"Removing {service_name} service")
        service_path = f"{self.base_path}/{service_name}"
        try:
            shutil.rmtree(service_path)
        except:
            logger.debug(f"Service {service_name} was already removed")
            pass

    def install_service(self, service_name: str, service_snapshot: DocumentSnapshot):
        """Given the service name and `DocumentSnapshot`, install the service from firebase."""
        logger.debug(f"Installing {service_name} Service")
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

    def compare(self, service_name: str, service_snapshot: DocumentSnapshot):
        """Return `True` if local and remote service are the same. If not return `False`."""
        remote_version = self._get_remote_version(service_snapshot)
        local_version = self._get_local_version(service_name)
        logger.debug(f"Local version: {local_version}")
        logger.debug(f"Remote version: {remote_version}")
        if local_version != remote_version:
            return False

        remote_envs = self._get_remote_envs(service_snapshot)
        local_envs = self._get_local_envs(service_name)
        logger.debug(f"Local envs: {local_envs}")
        logger.debug(f"Remote envs: {remote_envs}")
        return local_envs == remote_envs

    def on_client_initialized(self):
        """Callback function when the client is initialized."""
        logger.debug("Firestore client initialized")

    def on_server_not_responding(self):
        """Callback function when the server is not responding."""
        logger.error("Firestore server not responding")

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
        """For each change in the installed services update the local services in the iombian.

        There can be three type of changes:
            - ADDED: install the service from firebase.
            - REMOVED: remove the service from the iombian.
            - MODIFIED: update the service by removing and installing it again.
        """
        for change in changes:
            service_snapshot = change.document
            service_name = service_snapshot.id

            if change.type == ChangeType.ADDED:
                if service_name not in self.services:
                    try:
                        self.install_service(service_name, service_snapshot)
                        self.services.append(service_name)
                    except InvalidRemoteService:
                        pass

            elif change.type == ChangeType.REMOVED:
                self.remove_service(service_name)
                if service_name in self.services:
                    self.services.remove(service_name)

            elif change.type == ChangeType.MODIFIED:
                self.remove_service(service_name)
                try:
                    self.install_service(service_name, service_snapshot)
                except InvalidRemoteService:
                    if service_name in self.services:
                        self.services.remove(service_name)
