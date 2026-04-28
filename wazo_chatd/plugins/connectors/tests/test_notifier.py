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
        message.meta = Mock(type_='sms', backend='sms_backend', status='delivered')
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
        assert delivery['status'] == 'delivered'


class TestAsyncNotifierDeliveryStatusUpdated(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bus = Mock()
        self.notifier = AsyncNotifier(self.bus)
        self.room = Mock(
            uuid='room-uuid', tenant_uuid='tenant-uuid', users=[Mock(uuid='user-1')]
        )

    def _make_meta_and_record(self) -> tuple[Mock, Mock]:
        meta = Mock(
            message_uuid='msg-uuid',
            backend='sms_backend',
            message=Mock(user_uuid='user-1'),
        )
        record = Mock(
            status='sent', timestamp=datetime(2026, 3, 30, 14, tzinfo=timezone.utc)
        )
        return meta, record

    async def test_publishes_delivery_status_event(self) -> None:
        meta, record = self._make_meta_and_record()

        await self.notifier.delivery_status_updated(meta, record, self.room)

        self.bus.publish.assert_called_once()
        event = self.bus.publish.call_args[0][0]
        assert event.name == 'chatd_message_delivery_status'

    async def test_delivery_status_event_targets_sender_only(self) -> None:
        sender = Mock(uuid='sender-uuid')
        other = Mock(uuid='other-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid', users=[sender, other])
        meta = Mock(
            message_uuid='msg-uuid',
            backend='sms_backend',
            message=Mock(user_uuid='sender-uuid'),
        )
        record = Mock(
            status='sent', timestamp=datetime(2026, 3, 30, 14, tzinfo=timezone.utc)
        )

        await self.notifier.delivery_status_updated(meta, record, room)

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
        room = Mock(
            uuid='room-uuid',
            tenant_uuid='tenant-uuid',
            users=[sender, recipient],
        )
        meta = Mock(
            message_uuid='msg-uuid',
            backend='sms_backend',
            message=Mock(user_uuid='sender-uuid'),
        )
        record = Mock(
            status='delivered',
            timestamp=datetime(2026, 3, 30, 14, tzinfo=timezone.utc),
        )

        await self.notifier.delivery_status_updated(meta, record, room)

        events = [call.args[0] for call in self.bus.publish.call_args_list]
        status_events = [e for e in events if e.name == 'chatd_message_delivery_status']
        message_events = [
            e for e in events if e.name == 'chatd_user_room_message_created'
        ]
        assert len(status_events) == 1
        assert len(message_events) == 1
        assert message_events[0].user_uuid == 'recipient-uuid'

    async def test_non_delivered_status_does_not_publish_message_created(self) -> None:
        meta, record = self._make_meta_and_record()

        await self.notifier.delivery_status_updated(meta, record, self.room)

        events = [call.args[0] for call in self.bus.publish.call_args_list]
        message_events = [
            e for e in events if e.name == 'chatd_user_room_message_created'
        ]
        assert len(message_events) == 0

    async def test_publish_error_does_not_propagate(self) -> None:
        self.bus.publish.side_effect = RuntimeError('connection lost')
        meta, record = self._make_meta_and_record()

        await self.notifier.delivery_status_updated(meta, record, self.room)
