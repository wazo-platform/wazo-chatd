# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.connectors.bus_consume import ConnectorBusEventHandler


class TestConnectorBusEventHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.bus_consumer = Mock()
        self.router = Mock()
        self.handler = ConnectorBusEventHandler(self.bus_consumer, self.router)

    def test_subscribes_to_provider_events(self) -> None:
        self.handler.subscribe()

        event_names = [
            call.args[0] for call in self.bus_consumer.subscribe.call_args_list
        ]
        assert 'chat_provider_created' in event_names
        assert 'chat_provider_edited' in event_names
        assert 'chat_provider_deleted' in event_names

    def test_subscribes_to_user_alias_events(self) -> None:
        self.handler.subscribe()

        event_names = [
            call.args[0] for call in self.bus_consumer.subscribe.call_args_list
        ]
        assert 'user_alias_created' in event_names
        assert 'user_alias_deleted' in event_names

    def test_provider_created_invalidates_cache(self) -> None:
        self.handler.on_provider_created({'uuid': 'prov-1'})

        self.router.invalidate_cache.assert_called_once()

    def test_provider_edited_invalidates_cache(self) -> None:
        self.handler.on_provider_edited({'uuid': 'prov-1'})

        self.router.invalidate_cache.assert_called_once()

    def test_provider_deleted_invalidates_cache(self) -> None:
        self.handler.on_provider_deleted({'uuid': 'prov-1'})

        self.router.invalidate_cache.assert_called_once()

    def test_user_alias_created_invalidates_cache(self) -> None:
        self.handler.on_user_alias_created({'uuid': 'alias-1'})

        self.router.invalidate_cache.assert_called_once()

    def test_user_alias_deleted_invalidates_cache(self) -> None:
        self.handler.on_user_alias_deleted({'uuid': 'alias-1'})

        self.router.invalidate_cache.assert_called_once()
