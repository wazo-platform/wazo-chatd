# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.status import Status
from xivo_bus.consumer import BusConsumer as BaseConsumer
from xivo_bus.publisher import BusPublisher as BasePublisher


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
