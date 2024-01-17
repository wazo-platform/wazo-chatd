# Copyright 2019-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_bus.consumer import BusConsumer as BaseConsumer
from wazo_bus.publisher import BusPublisher as BasePublisher
from xivo.status import Status


class BusConsumer(BaseConsumer):
    @classmethod
    def from_config(cls, bus_config):
        return cls(name='wazo-chatd', **bus_config)

    def provide_status(self, status):
        status['bus_consumer']['status'] = (
            Status.ok if self.consumer_connected() else Status.fail
        )


class BusPublisher(BasePublisher):
    @classmethod
    def from_config(cls, service_uuid, bus_config):
        return cls(name='wazo-chatd', service_uuid=service_uuid, **bus_config)
