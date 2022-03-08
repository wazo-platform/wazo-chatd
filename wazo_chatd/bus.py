# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.status import Status
from xivo_bus.consumer import BusConsumer as BaseConsumer


class BusConsumer(BaseConsumer):
    def provide_status(self, status):
        status['bus_consumer']['status'] = (
            Status.ok if self.is_running else Status.fail
        )
