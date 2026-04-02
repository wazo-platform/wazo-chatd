# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from wazo_chatd.plugins.connectors.notifier import AsyncNotifier


class TestAsyncNotifierMessageCreated(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = AsyncNotifier(self.bus)

    def _make_message(self) -> Mock:
        message = Mock()
        message.uuid = 'msg-uuid'
        message.content = 'hello'
        message.alias = None
        message.user_uuid = 'user-uuid'
        message.tenant_uuid = 'tenant-uuid'
        message.wazo_uuid = 'wazo-uuid'
        message.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        message.room = Mock(uuid='room-uuid')
        return message

    async def test_publishes_event_per_user(self) -> None:
        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='user-1'), Mock(uuid='user-2')]

        await self.notifier.message_created(room, self._make_message())

        assert self.bus.publish.call_count == 2

    async def test_publishes_correct_event_type(self) -> None:
        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='user-1')]

        await self.notifier.message_created(room, self._make_message())

        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_user_room_message_created'


class TestAsyncNotifierDeliveryStatusUpdated(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = AsyncNotifier(self.bus)

    async def test_publishes_delivery_status_event(self) -> None:
        await self.notifier.delivery_status_updated(
            message_uuid='msg-uuid',
            status='sent',
            timestamp='2026-03-30T14:00:00+00:00',
            backend='twilio',
            tenant_uuid='tenant-uuid',
            room_uuid='room-uuid',
            user_uuids=['user-1'],
        )

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_message_delivery_status'

    async def test_publish_error_does_not_propagate(self) -> None:
        self.bus.publish.side_effect = RuntimeError('connection lost')

        await self.notifier.delivery_status_updated(
            message_uuid='msg-uuid',
            status='sent',
            timestamp='',
            backend='twilio',
            tenant_uuid='tenant-uuid',
            room_uuid='room-uuid',
            user_uuids=['user-1'],
        )
