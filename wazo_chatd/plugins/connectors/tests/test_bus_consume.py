# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.plugins.connectors.bus_consume import BusEventHandler


class TestBusEventHandler(unittest.TestCase):
    def test_on_external_auth_changed_invalidates_cache(self) -> None:
        router = Mock()
        handler = BusEventHandler(Mock(), router)
        payload = {
            'uuid': 'tenant-uuid',
            'external_auth_name': 'sms_backend',
        }

        handler.on_external_auth_changed(payload)

        router.invalidate_backend_cache.assert_called_once_with(
            'tenant-uuid', 'sms_backend'
        )

    def test_subscribe_registers_added_updated_and_deleted(self) -> None:
        bus = Mock()
        handler = BusEventHandler(bus, Mock())

        handler.subscribe()

        subscribed = {
            call.args[0]: call.args[1] for call in bus.subscribe.call_args_list
        }
        assert subscribed == {
            'auth_external_auth_added': handler.on_external_auth_changed,
            'auth_external_auth_updated': handler.on_external_auth_changed,
            'auth_external_auth_deleted': handler.on_external_auth_changed,
        }
