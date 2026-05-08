# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from wazo_chatd.plugins.connectors.notifier import AsyncNotifier, UserIdentityNotifier


class TestUserIdentityNotifier(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = UserIdentityNotifier(self.bus)

    def _make_identity(self) -> Mock:
        identity = Mock()
        identity.uuid = 'identity-uuid'
        identity.user_uuid = 'user-uuid'
        identity.tenant_uuid = 'tenant-uuid'
        identity.backend = 'sms_backend'
        identity.type_ = 'sms'
        identity.identity = '+15551234567'
        identity.extra = {}
        return identity

    def test_created_publishes_event(self) -> None:
        identity = self._make_identity()

        self.notifier.created(identity)

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_user_identity_created'
        assert event.content['uuid'] == 'identity-uuid'
        assert event.content['backend'] == 'sms_backend'
        assert event.content['type'] == 'sms'
        assert event.content['identity'] == '+15551234567'

    def test_updated_publishes_event(self) -> None:
        identity = self._make_identity()

        self.notifier.updated(identity)

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_user_identity_updated'

    def test_deleted_publishes_event(self) -> None:
        identity = self._make_identity()

        self.notifier.deleted(identity)

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_user_identity_deleted'
        assert event.content['uuid'] == 'identity-uuid'

    def test_event_targets_correct_user(self) -> None:
        identity = self._make_identity()

        self.notifier.created(identity)

        event = self.bus.publish.call_args[0][0]
        assert event.user_uuid == 'user-uuid'
        assert event.tenant_uuid == 'tenant-uuid'


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
        message.meta = Mock(type_='sms', backend='sms_backend', deliveries=[])
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

    async def test_event_includes_delivery(self) -> None:
        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='user-1')]

        await self.notifier.message_created(room, self._make_message())

        event = self.bus.publish.call_args[0][0]
        delivery = event.content['delivery']
        assert delivery['type'] == 'sms'
        assert delivery['backend'] == 'sms_backend'
        assert 'status' not in delivery


class TestAsyncNotifierDeliveryStatusUpdated(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = AsyncNotifier(self.bus)

    def _make_delivery_and_record(
        self,
        status: str = 'sent',
        sender_uuid: str = 'user-1',
        room_users: list[Mock] | None = None,
    ) -> tuple[Mock, Mock]:
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = room_users if room_users is not None else [Mock(uuid='user-1')]
        message = Mock(
            uuid='msg-uuid',
            content='hello',
            alias=None,
            user_uuid=sender_uuid,
            tenant_uuid='tenant-uuid',
            wazo_uuid='wazo-uuid',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            room=room,
        )
        meta = Mock(
            message_uuid='msg-uuid',
            type_='sms',
            backend='sms_backend',
            message=message,
            deliveries=[],
        )
        message.meta = meta
        delivery = Mock(
            id=1,
            recipient_identity='+15559876',
            external_id='ext-1',
            meta=meta,
        )
        record = Mock(
            status=status, timestamp=datetime(2026, 3, 30, 14, tzinfo=timezone.utc)
        )
        return delivery, record

    async def test_publishes_delivery_status_event(self) -> None:
        delivery, record = self._make_delivery_and_record()

        await self.notifier.delivery_status_updated(delivery, record)

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_message_delivery_status'
        assert event.content['recipient_identity'] == '+15559876'

    async def test_delivery_status_event_targets_sender_only(self) -> None:
        sender = Mock(uuid='sender-uuid')
        other = Mock(uuid='other-uuid')
        delivery, record = self._make_delivery_and_record(
            sender_uuid='sender-uuid', room_users=[sender, other]
        )

        await self.notifier.delivery_status_updated(delivery, record)

        event = next(
            e
            for e in (call.args[0] for call in self.bus.publish.call_args_list)
            if e.name == 'chatd_message_delivery_status'
        )
        assert event.user_uuid == 'sender-uuid'

    async def test_delivered_status_publishes_message_created_to_other_users(
        self,
    ) -> None:
        sender = Mock(uuid='sender-uuid', identity=None)
        recipient = Mock(uuid='recipient-uuid', identity=None)
        delivery, record = self._make_delivery_and_record(
            status='delivered',
            sender_uuid='sender-uuid',
            room_users=[sender, recipient],
        )

        await self.notifier.delivery_status_updated(delivery, record)

        events = [call.args[0] for call in self.bus.publish.call_args_list]
        status_events = [e for e in events if e.name == 'chatd_message_delivery_status']
        message_events = [
            e for e in events if e.name == 'chatd_user_room_message_created'
        ]
        assert len(status_events) == 1
        assert len(message_events) == 1
        assert message_events[0].user_uuid == 'recipient-uuid'

    async def test_non_delivered_status_does_not_publish_message_created(self) -> None:
        delivery, record = self._make_delivery_and_record()

        await self.notifier.delivery_status_updated(delivery, record)

        events = [call.args[0] for call in self.bus.publish.call_args_list]
        message_events = [
            e for e in events if e.name == 'chatd_user_room_message_created'
        ]
        assert len(message_events) == 0

    async def test_publish_error_does_not_propagate(self) -> None:
        self.bus.publish.side_effect = RuntimeError('connection lost')
        delivery, record = self._make_delivery_and_record()

        with self.assertLogs(
            'wazo_chatd.plugins.connectors.notifier', level='ERROR'
        ) as captured:
            await self.notifier.delivery_status_updated(delivery, record)

        assert any('Failed to publish' in line for line in captured.output)
