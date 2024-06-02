import os
import shutil
import logging
from typing import Any, Dict, List, Optional, TypedDict

import yaml
from google.cloud.firestore_v1 import Client, DocumentReference, DocumentSnapshot
from google.cloud.firestore_v1.watch import ChangeType, DocumentChange
from proto.datetime_helpers import DatetimeWithNanoseconds

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


class InstalledServicesDownloader:
    """Service that handles the installed services of the service and updates the local iombian services accordingly.

    To start the service call `read_local_services` and then `start`.
    """

    client: Client
    """Firestore database client."""
    user_id: str
    """Id of the owner of the device."""
    device_id: str
    """Id of the device."""
    device: DocumentReference
    """Reference to the firestore document of this device."""
    services: List[str]
    """The services in the local iombian."""
    base_path: str
    """The base path where the services are installed (normally "/opt/iombian-services")."""

    def __init__(
        self, client: Client, user_id: str, device_id: str, base_path: str
    ) -> None:
        self.client = client
        self.user_id = user_id
        self.device_id = device_id
        self.device = (
            client.collection("users")
            .document(user_id)
            .collection("devices")
            .document(device_id)
        )
        self.services = []
        self.base_path = base_path

    def _get_local_version(self, service_name: str) -> str:
        """Get the version of the local service given the service name.
        The local service is the one installed on the iombian.
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
            logger.warn(f"Invalid local serivce {service_name}")
            raise InvalidLocalService

    def _get_remote_version(self, service_snapshot: DocumentSnapshot) -> str:
        """Get the version of the remote service given the services `DocumentSnapshot`.
        The remote service is the one in firebase.
        """
        service_dict = service_snapshot.to_dict()
        if service_dict is None:
            logger.warn(f"Invalid remote serivce {service_snapshot.id}")
            raise InvalidRemoteService

        version = service_dict.get("version")
        if version is None:
            logger.warn(f"Invalid remote serivce {service_snapshot.id}")
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

                if value == "true":
                    value = True
                elif value == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                else:
                    try:
                        value = float(value)
                    except:
                        pass

                envs[key] = value
            return envs
        except:
            logger.warn(f"Invalid remote serivce {service_name}")
            raise InvalidLocalService

    def _get_remote_envs(self, service_snapshot: DocumentSnapshot) -> Dict[str, Any]:
        """Get the environment variables of the remote service given the services `DocumentSnapshot`.
        The remote service is the one installed in firebase.

        If the remote service has no fields or the fields don't have a env field raise a `InvalidRemoteService` error.
        """
        service_dict = service_snapshot.to_dict()
        if service_dict is None:
            logger.warn(f"Invalid remote serivce {service_snapshot.id}")
            raise InvalidRemoteService

        envs = service_dict.get("envs")
        if envs is None:
            logger.warn(f"Invalid remote serivce {service_snapshot.id}")
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
            service_reference = self.device.collection("installed_services").document(
                service_name
            )
            service_snapshot = service_reference.get()

            if service_snapshot.exists:
                try:
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
        """Start the listener, the `on_snapshot()` function, for tracking changes on firebase."""
        logger.info("Installed Services Downloader started.")
        self.watch = self.device.collection("installed_services").on_snapshot(
            self._on_installed_service_change
        )

    def stop(self):
        """Stop the downloader by stopping the listener."""
        logger.info("Installed Services Downloader stopped.")
        if self.watch is not None:
            self.watch.unsubscribe()

    def remove_service(self, service_name: str):
        """Given the service name, remove the service from the iombian."""
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
        if local_version != remote_version:
            return False

        remote_envs = self._get_remote_envs(service_snapshot)
        local_envs = self._get_local_envs(service_name)
        return local_envs == remote_envs

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
