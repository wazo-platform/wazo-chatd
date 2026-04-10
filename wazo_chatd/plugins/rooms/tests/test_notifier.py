# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.plugins.rooms.notifier import RoomNotifier


class TestRoomNotifierMessageCreated(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = RoomNotifier(self.bus)

    def test_internal_message_notifies_all_users(self) -> None:
        room = Mock()
        room.users = [
            Mock(uuid='user-a', identity=None),
            Mock(uuid='user-b', identity=None),
        ]
        message = Mock(meta=None, user_uuid='user-a')

        self.notifier.message_created(room, message)

        assert self.bus.publish.call_count == 2

    def test_outbound_pending_notifies_sender_only(self) -> None:
        room = Mock()
        room.users = [
            Mock(uuid='user-a', identity=None),
            Mock(uuid='user-b', identity=None),
        ]
        message = Mock(user_uuid='user-a')
        message.meta.status = 'pending'

        self.notifier.message_created(room, message)

        assert self.bus.publish.call_count == 1
        event = self.bus.publish.call_args[0][0]
        assert event.user_uuid == 'user-a'

    def test_inbound_delivered_notifies_all_users(self) -> None:
        room = Mock()
        room.users = [
            Mock(uuid='user-a', identity=None),
            Mock(uuid='user-b', identity=None),
        ]
        message = Mock(user_uuid='user-a')
        message.meta.status = 'delivered'

        self.notifier.message_created(room, message)

        assert self.bus.publish.call_count == 2

    def test_external_participants_not_notified(self) -> None:
        room = Mock()
        room.users = [
            Mock(uuid='user-a', identity=None),
            Mock(uuid='ext-user', identity='+15559876'),
        ]
        message = Mock(meta=None, user_uuid='user-a')

        self.notifier.message_created(room, message)

        assert self.bus.publish.call_count == 1
        event = self.bus.publish.call_args[0][0]
        assert event.user_uuid == 'user-a'
