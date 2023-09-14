# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.status import Status
from xivo_bus.consumer import BusConsumer as BaseConsumer
from xivo_bus.publisher import BusPublisher as BasePublisher


class BusConsumer(BaseConsumer):
    def __init__(self, subscribe=None, origin_uuid=None, **kwargs):
        self._headers = {'origin_uuid': origin_uuid}
        super().__init__(subscribe=subscribe, **kwargs)

    @classmethod
    def from_config(cls, bus_config, config):
        print(bus_config)
        return cls(name='wazo-chatd', origin_uuid=config['uuid'], **bus_config)

    def provide_status(self, status):
        status['bus_consumer']['status'] = (
            Status.ok if self.consumer_connected() else Status.fail
        )

    def subscribe(self, event, handler):
        return super().subscribe(event, handler, headers=self._headers)


class BusPublisher(BasePublisher):
    @classmethod
    def from_config(cls, service_uuid, bus_config):
        return cls(name='wazo-chatd', service_uuid=service_uuid, **bus_config)
