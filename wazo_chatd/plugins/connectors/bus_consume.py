# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wazo_chatd.bus import BusConsumer
    from wazo_chatd.plugins.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class ConnectorBusEventHandler:
    def __init__(self, bus_consumer: BusConsumer, router: ConnectorRouter) -> None:
        self._bus_consumer = bus_consumer
        self._router = router

    def subscribe(self) -> None:
        pass
