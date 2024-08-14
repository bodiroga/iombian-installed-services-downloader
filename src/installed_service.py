#!/usr/bin/env python3

import logging

from installed_local_service import InstalledLocalService, InvalidLocalService, WriteError
from installed_remote_service import InstalledRemoteService, UnconfiguredRemoteService, InvalidRemoteService

logger = logging.getLogger(__name__)


class InstallationFailed(Exception):
    """Error installing the service."""

class ReconfigurationFailed(Exception):
    """Error reconfiguring the service."""

class UpdateFailed(Exception):
    """Error updating the service."""


class InstalledService:
    """Class to handle all the functions of a installed service, both local and remote
    
    This class requires a local service and a remote service
    """

    service_name: str
    """Name of the service"""
    local_service: InstalledLocalService
    """Handler for the local functions of the installed service"""
    remote_service: InstalledRemoteService
    """Handler for the remote functions of the installed service"""

    def __init__(self, service_name: str, local_service: InstalledLocalService, remote_service: InstalledRemoteService) -> None:
        self.service_name = service_name
        self.local_service = local_service
        self.remote_service = remote_service

    def are_services_equal(self) -> bool:
        """Compare the versions of the local and remote services"""
        logger.debug(f"Comparing versions for '{self.service_name}' service")
        try:
            local_version = self.local_service.get_version()
            remote_version = self.remote_service.get_version()
            if local_version != remote_version:
                logger.warning("Local and remote versions are different")
                return False
            
            local_envs = self.local_service.get_envs()
            remote_envs = self.remote_service.get_envs()
            if local_envs != remote_envs:
                logger.warning("Local and remote envs are different")
                return False
            
            return True
        except (InvalidLocalService, UnconfiguredRemoteService, InvalidRemoteService) as error:
            logger.error(f"Invalid local or remote service: {error}")
            return False
        
    def upload_service(self) -> None:
        """Upload the local service info to the remote service"""
        logger.debug(f"Uploading '{self.service_name}' local service info to the remote service")
        try:
            version = self.local_service.get_version()
            envs = self.local_service.get_envs()

            self.remote_service.upload_service(version, envs)
            logger.info(f"'{self.service_name}' service info has been succesfully uploaded")
        except InvalidLocalService as error:
            logger.error(f"The upload service function could not finish: {error}")
       
    def install_service(self) -> None:
        """Install the service locally with the remote information"""
        logger.debug(f"Installing '{self.service_name}' service locally")
        self.local_service.create_folder()
        try:
            version = self.remote_service.get_version()
            compose = self.remote_service.get_marketplace_compose()
            envs = self.remote_service.get_envs()

            self.local_service.write_compose_file(compose)
            self.local_service.write_envs_file(envs)
            logger.info(f"'{self.service_name}' ({version}) service has been succesfully installed")

            self.remote_service.update_service_status("downloaded")
        except (UnconfiguredRemoteService, InvalidRemoteService, WriteError) as error:
            logger.error(f"The install service function could not finish: {error}")
            self.remote_service.update_service_status("unknown")
            raise InstallationFailed("Error installing the service")
        
    def reconfigure_service(self) -> None:
        """Reconfigure the service locally with the remote information"""
        logger.debug(f"Reconfiguring '{self.service_name}' service locally")
        try:
            envs = self.remote_service.get_envs()

            self.local_service.write_envs_file(envs)
            logger.info(f"'{self.service_name}' service has been succesfully reconfigured")

            self.remote_service.update_service_status("reconfigured")
        except (UnconfiguredRemoteService, InvalidRemoteService, WriteError) as error:
            logger.error(f"The reconfigure service function could not finish: {error}")
            self.remote_service.update_service_status("unknown")
            raise ReconfigurationFailed("Error reconfiguring the service")
        
    def update_service(self) -> None:
        """Update the service locally with the remote information"""
        logger.debug(f"Updating '{self.service_name}' service locally")
        try:
            version = self.remote_service.get_version()
            compose = self.remote_service.get_marketplace_compose()
            envs = self.remote_service.get_envs()

            self.local_service.write_compose_file(compose)
            self.local_service.write_envs_file(envs)
            logger.info(f"'{self.service_name}' ({version}) service has been succesfully updated")

            self.remote_service.update_service_status("updated")
        except (UnconfiguredRemoteService, InvalidRemoteService, WriteError) as error:
            logger.error(f"The update service function could not finish: {error}")
            self.remote_service.update_service_status("unknown")
            raise UpdateFailed("Error updating the service")
        
    def remove_service(self) -> None:
        """Remove the service locally and remotely"""
        logger.debug(f"Removing '{self.service_name}' service completely")

        self.local_service.remove_service()
        self.remote_service.remove_service()
        logger.info(f"'{self.service_name}' service has been completely removed")
