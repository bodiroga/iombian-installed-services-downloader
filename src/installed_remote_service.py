#!/usr/bin/env python3

import logging

from typing import Any, Dict, Optional
from google.cloud.firestore import Client, DocumentReference, DocumentSnapshot

logger = logging.getLogger(__name__)


class UnconfiguredRemoteService(Exception):
    """Remote service snapshot info is not configured."""


class InvalidRemoteService(Exception):
    """Remote service is invalid."""


class EmptyDocumentSnapshot(DocumentSnapshot):
    """Empty DocumentSnapshot class to avoid errors when testing."""
    def __init__(self) -> None:
        pass

    def to_dict(self) -> Dict:
        return {}


class InstalledRemoteService:
    """Class to handle the remote functions of a installed service"""

    service_name: str
    """Name of the service"""
    device: DocumentReference
    """Reference to the remote device"""
    client: Client
    """Firestore client"""
    service_snapshot: DocumentSnapshot
    """Snapshot of the remote service information"""
    service_dict: Dict[str, Any]
    """Dictionary of the remote service information"""

    def __init__(self, service_name: str, device: DocumentReference, client: Client, service_snapshot: DocumentSnapshot = EmptyDocumentSnapshot()):
        self.service_name = service_name
        self.device = device
        self.client = client
        self.service_snapshot = service_snapshot
        self.service_dict = self._get_service_dict()

    def _get_service_dict(self) -> Dict[str, Any]:
        service_dict = self.service_snapshot.to_dict()
        if not service_dict:
            return {}
        return service_dict
    
    def get_version(self) -> str:
        """Get the version of the service"""
        logger.debug(f"Getting remote version for '{self.service_name}' service")
        if not self.service_dict: raise UnconfiguredRemoteService(f"Service snapshot is not valid: {self.service_snapshot}")
        if "version" not in self.service_dict: raise InvalidRemoteService(f"'version' key not found in service dict: {self.service_dict}")
        return self.service_dict.get("version", "")
    
    def get_status(self) -> str:
        """Get the status of the service"""
        logger.debug(f"Getting remote status for '{self.service_name}' service")
        if not self.service_dict: raise UnconfiguredRemoteService(f"Service snapshot is not valid: {self.service_snapshot}") 
        if "status" not in self.service_dict: raise InvalidRemoteService(f"'status' key not found in service dict: {self.service_dict}")
        return self.service_dict.get("status", "")
    
    def get_envs(self) -> Dict[str, Any]:
        """Get the environment variables of the service"""
        logger.debug(f"Getting remote envs for '{self.service_name}' service")
        if not self.service_dict: raise UnconfiguredRemoteService(f"Service snapshot is not valid: {self.service_snapshot}")
        if "envs" not in self.service_dict: raise InvalidRemoteService(f"'envs' key not found in service dict: {self.service_dict}")
        return self.service_dict.get("envs", {})
    
    def get_marketplace_compose(self, version: Optional[str] = None) -> Dict[str, Any]:
        """Get the docker compose file of the specific version from the marketplace"""
        logger.debug(f"Getting remote compose file for '{self.service_name}' service")
        try:
            version = self.get_version() if not version else version
        except (UnconfiguredRemoteService, InvalidRemoteService) as error:
            raise error
        
        marketplace_service = self.client.document(f"services/{self.service_name}/versions/{version}").get().to_dict()
        if not marketplace_service:
            raise InvalidRemoteService(f"'{self.service_name}'->'{version}' service not found in the marketplace")
        
        return marketplace_service.get("compose", {})

    def upload_service(self, local_version: str, local_envs: Dict[str, Any], status: str = "started") -> None:
        """Upload the service info to the remote device"""
        logger.debug(f"Uploading '{self.service_name}' ({local_version}) service to the remote device")
        service_reference = self.device.collection("installed_services").document(self.service_name)
        service_reference.set(
            {"version": local_version,
              "status": status,
                "envs": local_envs}
        )
        logger.debug(f"'{self.service_name}' ({local_version}) service info uploaded to the remote device")

    def update_service_status(self, service_status: str) -> None:
        """Update the service status of the remote device."""
        logger.debug(f"Updating '{self.service_name}' service status to {service_status} in remote device")
        service_reference = self.device.collection("installed_services").document(
            self.service_name
        )
        service_reference.update({"status": service_status})

    def remove_service(self) -> None:
        """Remove the service info from the remote device."""
        logger.debug(f"Removing '{self.service_name}' service from Firebase")
        service_reference = self.device.collection("installed_services").document(
            self.service_name
        )
        service_reference.delete()
