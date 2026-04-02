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
        self.pubsub = Mock()
        self.service = RoomService(
            WAZO_UUID,
            self.dao,
            self.notifier,
            self.pubsub,
        )
        self.room = Mock()
        self.message = Mock(wazo_uuid=None)

    def test_create_message_persists_and_notifies(self) -> None:
        result = self.service.create_message(self.room, self.message)

        self.dao.room.add_message.assert_called_once_with(self.room, self.message)
        self.notifier.message_created.assert_called_once_with(self.room, self.message)
        assert result is self.message
        assert self.message.wazo_uuid == WAZO_UUID

    def test_create_message_publishes_to_pubsub(self) -> None:
        self.service.create_message(self.room, self.message)

        self.pubsub.publish.assert_called_once_with(
            'room_message_created', (self.room, self.message)
        )

    def test_create_message_notifies_even_when_publishing(self) -> None:
        self.service.create_message(self.room, self.message)

        self.pubsub.publish.assert_called_once()
        self.notifier.message_created.assert_called_once_with(self.room, self.message)
