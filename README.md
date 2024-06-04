# IoMBian Installed Services Downloader

This service handles the firebase service installed services and updates the local iombian services accordingly.

`installed_services` is a collection on each device that determines what services are installed on a device.
Each document in the collection is a service, and its structure is this:
```
{
    version: "0.1.0",
    env: {
        LOG_LEVEL: "INFO",
        BUTTON_EVENTS_PORT: 5556,
        ...
    }
}
```

When a service is added, removed or modified in the installed services, the local services are updated unless the service structure is not correct.

## Installation

- Define project name in an environment variable:

> ```PROJECT_NAME=iombian-installed-services-downloader```

- Clone the repo into a temp folder:

> ```git clone https://github.com/Tknika/${PROJECT_NAME}.git /tmp/${PROJECT_NAME} && cd /tmp/${PROJECT_NAME}```

- Create the installation folder and move the appropriate files (edit the user):

> ```sudo mkdir /opt/${PROJECT_NAME}```

> ```sudo cp requirements.txt /opt/${PROJECT_NAME}```

> ```sudo cp -r src/* /opt/${PROJECT_NAME}```

> ```sudo cp systemd/${PROJECT_NAME}.service /etc/systemd/system/```

> ```sudo chown -R iompi:iompi /opt/${PROJECT_NAME}```

- Create the virtual environment and install the dependencies:

> ```cd /opt/${PROJECT_NAME}```

> ```python3 -m venv .venv```

> ```source .venv/bin/activate```

> ```pip install --upgrade pip```

> ```pip install -r requirements.txt```

- Start the script

> ```sudo systemctl enable ${PROJECT_NAME}.service && sudo systemctl start ${PROJECT_NAME}.service```

## Docker
To build the docker image, from the cloned repository, execute the docker build command in the same level as the Dockerfile:

```
docker build -t ${IMAGE_NAME}:${IMAGE_VERSION} .
```

For example `docker build -t iombian-installed-services-downloader:latest .`

After building the image, execute it with docker run:

```
docker run --name ${CONTAINER_NAME} --rm -d -v /opt/iombian-services:/opt/iombian-services -e BASE_PATH=/opt/iombian-services iombian-installed-services-downloader:latest
```

- **--name** is used to define the name of the created container.
- **--rm** can be used to delete the container when it stops. This parameter is optional.
- **-d** is used to run the container detached. This way the container will run in the background. This parameter is optional.
- **-v** is used to pass volumes to the container.
The volume passed is the **/opt/iombian-services** and is the folder where the installed services are stored.
- **-e** can be used to define the environment variables:
    - BASE_PATH: the path where the installed services are stored.
    Default value is "/opt/iombian-services".
    - CONFIG_HOST: the host of the config file handler service.
    Default value is "127.0.0.1".
    - CONFIG_PORT: the port of the config file handler service.
    Default value is 5555.
    - LOG_LEVEL: define the log level for the python logger.
    This can be DEBUG, INFO, WARN or ERROR.
    Default value is INFO.

Otherwise, a `docker-compose.yml` file can also be used to launch the container:

```
version: 3

services:
  iombian-installed-services-downloader:
    image: iombian-installed-services-downloader:latest
    container_name: iombian-installed-services-downloader
    restart: unless_stopped
    volumes:
      - /opt/iombian-services:/opt/iombian-services
    environment:
      CONFIG_HOST: "iombian-config-file-handler"
      CONFIG_PORT: 5555
      BASE_PATH: "/opt/iombian-services"
      LOG_LEVEL: "INFO"
```

```
docker compose up -d
```

## Author
(c) 2024 IoMBian team ([Aitor Iturrioz Rodríguez](https://github.com/bodiroga), [Aitor Castaño Mesa](https://github.com/aitorcas23)).

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
