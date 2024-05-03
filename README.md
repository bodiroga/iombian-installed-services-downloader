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
