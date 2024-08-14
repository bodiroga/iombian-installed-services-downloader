#!/usr/bin/env python3

import logging
import os
import shutil
import yaml

from typing import Any, Dict

logger = logging.getLogger(__name__)


class InvalidLocalService(Exception):
    """Local service is invalid."""

class InvalidComposeContent(Exception):
    """Compose information is invalid."""

class WriteError(Exception):
    """Error writing to file."""


class InstalledLocalService:
    """Class to handle the local functions of a installed service"""

    service_name: str
    """Name of the service"""
    base_path: str
    """Base path of the services"""
    service_folder: str
    """Folder of the service"""
    compose_file_path: str
    """Path of the service compose file"""
    envs_file_path: str
    """Path of the service envs file"""

    def __init__(self, service_name: str, base_path: str) -> None:
        self.service_name = service_name
        self.base_path = base_path
        self.service_folder = f"{base_path}/{service_name}"
        self.compose_file_path = f"{self.service_folder}/docker-compose.yaml"
        self.envs_file_path = f"{self.service_folder}/.env"

    def get_version(self) -> str:
        """Get the version of the service"""
        logger.debug(f"Getting local version for '{self.service_name}' service")
        try:
            with open(self.compose_file_path, "r") as docker_compose_txt:
                docker_compose = yaml.safe_load(docker_compose_txt)

            local_version = docker_compose.get("services", {}).get(self.service_name, {}).get("labels", {}).get(
                f"com.{self.service_name}.service.version", ""
            )
            if not local_version:
                raise InvalidLocalService(f"Local '{self.compose_file_path}' file does not contain any version")
            return local_version
        except (FileNotFoundError, OSError, yaml.YAMLError):
            raise InvalidLocalService(f"Local '{self.compose_file_path}' file could not be opened or read")
        
    def get_envs(self) -> Dict[str, Any]:
        """Get the environment variables of the service"""
        logger.debug(f"Getting local envs for '{self.service_name}' service")
        try:
            envs: Dict[str, Any] = {}
            with open(self.envs_file_path, "r") as envs_txt:
                lines = envs_txt.readlines()

            for line in lines:
                if "\n" in line:
                    line = line[:-1]
                key, value = line.split("=")
                envs[key] = value
            return envs
        except (FileNotFoundError, OSError):
            raise InvalidLocalService(f"Local '{self.envs_file_path}' file could not be opened or read")

    def create_folder(self) -> None:
        """Create the service folder in the local installation"""
        logger.debug(f"Creating '{self.service_name}' service folder locally")
        try:
            os.mkdir(self.service_folder)
        except FileExistsError:
            logger.debug(f"Service {self.service_name} folder already exists")
            return
        logger.debug(f"'{self.service_name}' service folder has been locally created")
        
    def remove_service(self) -> None:
        """Remove the service from the local installation"""
        logger.debug(f"Removing '{self.service_name}' service locally")
        try:
            shutil.rmtree(self.service_folder)
        except:
            logger.debug(f"Service {self.service_name} was already removed locally")
            return
        logger.debug(f"'{self.service_name}' service has been locally removed")

    def write_compose_file(self, compose_dict: Dict[str, Any]) -> None:
        """Write the provided compose content to the local installation"""
        logger.debug(f"Writing compose content to file for '{self.service_name}' service")
        try:
            compose_version = self._get_compose_dict_version(compose_dict)
            with open(self.compose_file_path, "w") as compose_file:
                yaml.dump(compose_dict, compose_file)
        except (FileNotFoundError, OSError, yaml.YAMLError, InvalidComposeContent):
            logger.error("Error writing to compose file")
            raise WriteError(f"Local '{self.compose_file_path}' file could not be written")
        logger.debug(f"Compose content for '{self.service_name}' ({compose_version}) service has been written")

    def write_envs_file(self, envs_dict: Dict[str, Any]) -> None:
        """Write the provided envs content to the local installation"""
        logger.debug(f"Writing envs content to file for '{self.service_name}' service")
        envs_list = [f"{key}={envs_dict[key]}\n" for key in envs_dict]
        try:
            with open(self.envs_file_path, "w") as envs_file:
                envs_file.writelines(envs_list)
        except (FileNotFoundError, OSError):
            logger.error("Error writing to envs file")
            raise WriteError(f"Local '{self.envs_file_path}' file could not be written")
        logger.debug(f"Envs content for '{self.service_name}' service has been written")

    def _get_compose_dict_version(self, compose_dict: Dict[str, Any]) -> str:
        """Get the specific version of the compose dictionary """
        logger.debug(f"Getting compose dict version")
        version = (compose_dict.get("services", {})
                            .get(self.service_name, {})
                            .get("labels", {})
                            .get(f"com.{self.service_name}.service.version", ""))
        if not version:
            logger.error(f"The compose content for '{self.service_name}' does not contain any version")
            raise InvalidComposeContent(f"The compose content for '{self.service_name}' does not contain any version")
        return version
