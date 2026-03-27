# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.plugins.rooms.services import RoomService

WAZO_UUID = 'test-wazo-uuid'


class TestRoomServiceCreateMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.dao = Mock()
        self.notifier = Mock()
        self.connector_router = Mock()
        self.service = RoomService(
            WAZO_UUID,
            self.dao,
            self.notifier,
            self.connector_router,
        )
        self.room = Mock()
        self.message = Mock(wazo_uuid=None)

    def test_create_message_persists_and_notifies(self) -> None:
        result = self.service.create_message(self.room, self.message)

        self.dao.room.add_message.assert_called_once_with(self.room, self.message)
        self.notifier.message_created.assert_called_once_with(self.room, self.message)
        assert result is self.message
        assert self.message.wazo_uuid == WAZO_UUID

    def test_create_message_routes_through_connector(self) -> None:
        self.service.create_message(self.room, self.message, route=True)

        self.connector_router.send.assert_called_once_with(self.room, self.message)

    def test_create_message_skips_routing_when_route_false(self) -> None:
        self.service.create_message(self.room, self.message, route=False)

        self.connector_router.send.assert_not_called()

    def test_create_message_routes_by_default(self) -> None:
        self.service.create_message(self.room, self.message)

        self.connector_router.send.assert_called_once()

    def test_create_message_without_connector_router(self) -> None:
        service = RoomService(WAZO_UUID, self.dao, self.notifier)

        result = service.create_message(self.room, self.message)

        self.dao.room.add_message.assert_called_once()
        self.notifier.message_created.assert_called_once()
        assert result is self.message

    def test_create_message_notifies_even_when_routing(self) -> None:
        self.service.create_message(self.room, self.message, route=True)

        self.notifier.message_created.assert_called_once_with(self.room, self.message)
