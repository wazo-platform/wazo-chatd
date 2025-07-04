# Copyright 2023-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase
from unittest.mock import Mock

from ..bus_consume import BusEventHandler


class TestBusEventHandler(TestCase):
    def setUp(self):
        self.dao = Mock()
        self.notifier = Mock()
        self.initiator_thread = Mock()
        self.handler = BusEventHandler(self.dao, self.notifier, self.initiator_thread)

    def test_on_device_state_change_ignored_on_hints(self):
        event = {
            'State': 'unavailable',
            'Device': 'Custom:*7351033***223',
        }
        self.handler._device_state_change(event)
        self.dao.endpoint.find_or_create.assert_not_called()

        event = {
            'State': 'unavailable',
            'Device': 'MWI:1001@internal',
        }
        self.handler._device_state_change(event)
        self.dao.endpoint.find_or_create.assert_not_called()

        event = {
            'State': 'unavailable',
            'Device': 'Queue:grp-01wazo-e0cc9e04-a40f-4d1d-ac51-58634b1cf5b3_avail',
        }
        self.handler._device_state_change(event)
        self.dao.endpoint.find_or_create.assert_not_called()
