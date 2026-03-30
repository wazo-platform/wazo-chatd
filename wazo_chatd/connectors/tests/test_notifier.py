# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from wazo_chatd.connectors.notifier import AsyncNotifier


class TestAsyncNotifierMessageCreated(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = AsyncNotifier(self.bus)

    async def test_publishes_event_per_user(self) -> None:
        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='user-1'), Mock(uuid='user-2')]

        message = Mock()

        with patch(
            'wazo_chatd.connectors.notifier.MessageSchema'
        ) as mock_schema:
            mock_schema.return_value.dump.return_value = {'uuid': 'msg-uuid'}
            await self.notifier.message_created(room, message)

        assert self.bus.publish.call_count == 2

    async def test_publishes_correct_event_type(self) -> None:
        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='user-1')]

        message = Mock()

        with patch(
            'wazo_chatd.connectors.notifier.MessageSchema'
        ) as mock_schema:
            mock_schema.return_value.dump.return_value = {'uuid': 'msg-uuid'}
            await self.notifier.message_created(room, message)

        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_user_room_message_created'


class TestAsyncNotifierDeliveryStatusUpdated(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = AsyncNotifier(self.bus)

    async def test_publishes_delivery_status_event(self) -> None:
        delivery = Mock()
        delivery.message_uuid = 'msg-uuid'
        delivery.backend = 'twilio'
        delivery.records = [Mock(status='sent')]
        delivery.message = Mock()
        delivery.message.room = Mock()
        delivery.message.room.uuid = 'room-uuid'
        delivery.message.room.tenant_uuid = 'tenant-uuid'
        delivery.message.room.users = [Mock(uuid='user-1')]

        await self.notifier.delivery_status_updated(delivery)

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_message_delivery_status'

    async def test_skips_when_no_message(self) -> None:
        delivery = Mock()
        delivery.message = None

        await self.notifier.delivery_status_updated(delivery)

        self.bus.publish.assert_not_called()

    async def test_skips_when_no_room(self) -> None:
        delivery = Mock()
        delivery.message = Mock()
        delivery.message.room = None

        await self.notifier.delivery_status_updated(delivery)

        self.bus.publish.assert_not_called()

    async def test_publish_error_does_not_propagate(self) -> None:
        self.bus.publish.side_effect = RuntimeError('connection lost')

        delivery = Mock()
        delivery.message_uuid = 'msg-uuid'
        delivery.backend = 'twilio'
        delivery.records = [Mock(status='sent')]
        delivery.message = Mock()
        delivery.message.room = Mock()
        delivery.message.room.uuid = 'room-uuid'
        delivery.message.room.tenant_uuid = 'tenant-uuid'
        delivery.message.room.users = [Mock(uuid='user-1')]

        await self.notifier.delivery_status_updated(delivery)
