# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.plugins.connectors.bus_consume import ConnectorBusEventHandler


class TestConnectorBusEventHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.bus_consumer = Mock()
        self.router = Mock()
        self.handler = ConnectorBusEventHandler(self.bus_consumer, self.router)

    def test_subscribe_is_noop(self) -> None:
        self.handler.subscribe()

        self.bus_consumer.subscribe.assert_not_called()
