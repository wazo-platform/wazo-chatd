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
