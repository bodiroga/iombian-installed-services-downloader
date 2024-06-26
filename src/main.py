import logging
import os
import signal

from communication_module import CommunicationModule
from installed_services_downloader import InstalledServicesDownloader

LOG_LEVEL = os.environ.get("LOG_LEVEL", logging.INFO)
CONFIG_HOST = os.environ.get("CONFIG_HOST", "127.0.0.1")
CONFIG_PORT = int(os.environ.get("CONFIG_PORT", 5555))
BASE_PATH = os.environ.get("BASE_PATH", "/opt/iombian-services")

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s - %(name)-16s - %(message)s", level=LOG_LEVEL
)
logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    logger.warn("Stopping the service")
    comm_module.stop()
    installed_services_downloader.stop()


if __name__ == "__main__":
    comm_module = CommunicationModule(host=CONFIG_HOST, port=CONFIG_PORT)
    comm_module.start()

    api_key = str(comm_module.execute_command("get_api_key"))
    project_id = str(comm_module.execute_command("get_project_id"))
    refresh_token = str(comm_module.execute_command("get_refresh_token"))
    device_id = str(comm_module.execute_command("get_device_id"))

    if not (api_key and project_id and refresh_token and device_id):
        exit(
            "Wasn't able to get the necessary information from the config file handler"
        )

    installed_services_downloader = InstalledServicesDownloader(
        api_key, project_id, refresh_token, device_id, BASE_PATH
    )
    installed_services_downloader.start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.pause()
