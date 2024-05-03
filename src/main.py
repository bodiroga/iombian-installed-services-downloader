import logging
import os

from communication_module import CommunicationModule
from default_firestore_client import DefaultFirestoreClient
from installed_services_downloader import InstalledServicesDownloader

LOG_LEVEL = os.environ.get("LOG_LEVEL", logging.INFO)
CONFIG_HOST = os.environ.get("CONFIG_HOST", "127.0.0.1")
CONFIG_PORT = int(os.environ.get("CONFIG_PORT", 5555))
BASE_PATH = os.environ.get("BASE_PATH", "/opt/iombian-services")

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s - %(name)-16s - %(message)s", level=LOG_LEVEL
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    comm_module = CommunicationModule(host=CONFIG_HOST, port=CONFIG_PORT)
    comm_module.start()

    api_key = str(comm_module.execute_command("get_api_key"))
    project_id = str(comm_module.execute_command("get_project_id"))
    refresh_token = str(comm_module.execute_command("get_refresh_token"))
    device_id = str(comm_module.execute_command("get_device_id"))

    if not (api_key and project_id and refresh_token and device_id):
        exit("Wasn't able to get the necessary information from the config file handler")

    client = DefaultFirestoreClient(api_key, project_id, refresh_token)
    client.initialize_client()

    if client.client is None or client.user_id is None:
        exit("The firebase client was not created correctly")

    installed_services_downloader = InstalledServicesDownloader(
        client.client, client.user_id, device_id, BASE_PATH
    )
    installed_services_downloader.read_local_services()
    installed_services_downloader.start()
