# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_bus.consumer import BusConsumer as BaseConsumer
from wazo_bus.publisher import BusPublisher as BasePublisher
from xivo.status import Status


class BusConsumer(BaseConsumer):
    @classmethod
    def from_config(cls, bus_config):
        return cls(name='wazo-chatd', **bus_config)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscribe_decorators = []

    def subscribe(self, event_name, handler):
        new_handler = handler
        for decorator in self.subscribe_decorators:
            new_handler = decorator(new_handler)
        super().subscribe(event_name, new_handler)

    def provide_status(self, status):
        status['bus_consumer']['status'] = (
            Status.ok if self.consumer_connected() else Status.fail
        )


class BusPublisher(BasePublisher):
    @classmethod
    def from_config(cls, service_uuid, bus_config):
        return cls(name='wazo-chatd', service_uuid=service_uuid, **bus_config)
