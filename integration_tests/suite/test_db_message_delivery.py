# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for room/message-delivery DAO methods."""

from __future__ import annotations

import pytest

from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import MessageDelivery, MessageMeta, Room, RoomMessage
from wazo_chatd.database.queries.async_.room import AsyncRoomDAO
from wazo_chatd.exceptions import DuplicateExternalIdException

from .helpers import fixtures
from .helpers.async_ import run_async
from .helpers.base import DBIntegrationTest, use_asset


def _build_message(
    room: Room,
    *,
    backend: str,
    external_id: str | None,
    recipient_identity: str = '+15559876',
    type_: str = 'sms',
) -> RoomMessage:
    sender = room.users[0]

    delivery = MessageDelivery(
        recipient_identity=recipient_identity,
        backend=backend,
        type_=type_,
        external_id=external_id,
    )

    return RoomMessage(
        content='hello',
        user_uuid=sender.uuid,
        tenant_uuid=room.tenant_uuid,
        wazo_uuid=sender.wazo_uuid,
        meta=MessageMeta(deliveries=[delivery]),
    )


@use_asset('database')
class TestAddMessage(DBIntegrationTest):
    @fixtures.db.room(users=[{}])
    @run_async
    async def test_duplicate_external_id_raises(self, room):
        dao = AsyncRoomDAO()
        await dao.add_message(
            room, _build_message(room, backend='twilio', external_id='SM_DUP_1')
        )
        with pytest.raises(DuplicateExternalIdException):
            await dao.add_message(
                room,
                _build_message(room, backend='twilio', external_id='SM_DUP_1'),
            )

    @fixtures.db.room(users=[{}])
    @run_async
    async def test_null_external_id_repeats_allowed(self, room):
        dao = AsyncRoomDAO()
        await dao.add_message(
            room,
            _build_message(
                room,
                backend='twilio',
                external_id=None,
                recipient_identity='+15559876',
            ),
        )
        await dao.add_message(
            room,
            _build_message(
                room,
                backend='twilio',
                external_id=None,
                recipient_identity='+15558888',
            ),
        )


@use_asset('database')
class TestPreparePendingDelivery(DBIntegrationTest):
    @fixtures.db.room(users=[{}])
    def test_creates_meta_with_one_delivery_per_recipient(self, room):
        sender = room.users[0]
        message = RoomMessage(
            content='hello',
            user_uuid=sender.uuid,
            tenant_uuid=room.tenant_uuid,
            wazo_uuid=sender.wazo_uuid,
            room_uuid=room.uuid,
        )

        self._dao.room.prepare_pending_delivery(
            message,
            recipient_identities=['+15559876'],
            backend='twilio',
            type_='sms',
        )
        self._dao.room.add_message(room, message)

        self._session.refresh(message)
        assert message.meta is not None
        assert message.meta.backend == 'twilio'
        assert len(message.meta.deliveries) == 1
        delivery = message.meta.deliveries[0]
        assert delivery.recipient_identity == '+15559876'
        assert delivery.records[0].status == DeliveryStatus.PENDING.value


@use_asset('database')
class TestFindTenantByExternalId(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'tracked',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_LOOKUP',
                        'statuses': ['pending', 'accepted'],
                    }
                ],
            }
        ]
    )
    def test_join_through_message_delivery(self, room):
        result = self._dao.room.find_tenant_by_external_id('SM_LOOKUP', 'twilio')
        assert result == str(room.tenant_uuid)

    @fixtures.db.room(messages=[{'content': 'no external'}])
    def test_returns_none_when_not_found(self, room):
        assert self._dao.room.find_tenant_by_external_id('SM_MISSING', 'twilio') is None


@use_asset('database')
class TestAsyncGetMessageMetaByExternalId(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'looked up',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_FETCH',
                        'statuses': ['pending'],
                    }
                ],
            }
        ]
    )
    @run_async
    async def test_returns_meta_and_eager_loads_deliveries(self, room):
        dao = AsyncRoomDAO()
        meta = await dao.get_message_meta_by_external_id('SM_FETCH', 'twilio')

        assert meta is not None
        assert meta.backend == 'twilio'
        assert len(meta.deliveries) == 1
        assert meta.deliveries[0].external_id == 'SM_FETCH'

    @fixtures.db.room(messages=[{'content': 'no meta'}])
    @run_async
    async def test_returns_none_when_external_id_not_found(self, room):
        dao = AsyncRoomDAO()
        assert await dao.get_message_meta_by_external_id('SM_MISSING', 'twilio') is None


@use_asset('database')
class TestAsyncListPendingExternalIds(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'pending msg',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_PENDING',
                        'statuses': ['accepted'],
                    }
                ],
            },
            {
                'content': 'delivered msg',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_DONE',
                        'statuses': ['accepted', 'delivered'],
                    }
                ],
            },
            {
                'content': 'other backend',
                'meta': {'type_': 'sms', 'backend': 'vonage'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'VG_PENDING',
                        'statuses': ['accepted'],
                    }
                ],
            },
        ]
    )
    @run_async
    async def test_returns_only_non_terminal_for_backend(self, room):
        dao = AsyncRoomDAO()
        result = await dao.list_pending_external_ids(
            tenant_uuid=str(room.tenant_uuid), backend='twilio'
        )

        assert result == ['SM_PENDING']


@use_asset('database')
class TestAsyncAddDeliveryRecord(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'tracked',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['pending']}
                ],
            }
        ]
    )
    @run_async
    async def test_record_anchored_to_delivery(self, room):
        delivery = room.messages[0].meta.deliveries[0]
        dao = AsyncRoomDAO()

        record = await dao.add_delivery_record(
            delivery, DeliveryStatus.ACCEPTED, reason='ok'
        )

        assert record.delivery_id == delivery.id
        assert record.status == DeliveryStatus.ACCEPTED.value
        assert record.reason == 'ok'


@use_asset('database')
class TestAsyncFindMatchingSignature(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'echo me',
                'meta': {
                    'type_': 'sms',
                    'backend': 'twilio',
                    'extra': {'message_signature': 'sig-abc'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['accepted']}
                ],
            }
        ]
    )
    @run_async
    async def test_returns_meta_when_signature_matches_within_window(self, room):
        dao = AsyncRoomDAO()
        meta = await dao.find_matching_signature(str(room.uuid), 'sig-abc')
        assert meta is not None
        assert meta.message_uuid == room.messages[0].uuid

    @fixtures.db.room(
        messages=[
            {
                'content': 'no match',
                'meta': {
                    'type_': 'sms',
                    'backend': 'twilio',
                    'extra': {'message_signature': 'sig-abc'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['accepted']}
                ],
            }
        ]
    )
    @run_async
    async def test_returns_none_when_signature_outside_window(self, room):
        dao = AsyncRoomDAO()
        assert (
            await dao.find_matching_signature(
                str(room.uuid), 'sig-abc', window_seconds=0
            )
            is None
        )

    @fixtures.db.room(
        messages=[
            {
                'content': 'in room A',
                'meta': {
                    'type_': 'sms',
                    'backend': 'twilio',
                    'extra': {'message_signature': 'sig-abc'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['accepted']}
                ],
            }
        ]
    )
    @fixtures.db.room()
    @run_async
    async def test_returns_none_for_different_room(self, room_a, room_b):
        dao = AsyncRoomDAO()
        assert await dao.find_matching_signature(str(room_b.uuid), 'sig-abc') is None


@use_asset('database')
class TestAsyncCheckDuplicateIdempotencyKey(DBIntegrationTest):
    @fixtures.db.user_identity(backend='twilio', type_='sms', identity='+15559876')
    @fixtures.db.room(
        messages=[
            {
                'content': 'with key',
                'meta': {
                    'type_': 'sms',
                    'backend': 'twilio',
                    'extra': {'inbound_idempotency_key': 'idem-123'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['delivered']}
                ],
            }
        ]
    )
    @run_async
    async def test_returns_true_when_key_present(self, room, identity):
        dao = AsyncRoomDAO()
        assert (
            await dao.check_duplicate_idempotency_key(
                'idem-123',
                recipient='+15559876',
                backend='twilio',
                window_seconds=3600,
            )
            is True
        )

    @fixtures.db.user_identity(backend='twilio', type_='sms', identity='+15559876')
    @fixtures.db.room(messages=[{'content': 'no key'}])
    @run_async
    async def test_returns_false_when_key_absent(self, room, identity):
        dao = AsyncRoomDAO()
        assert (
            await dao.check_duplicate_idempotency_key(
                'idem-missing',
                recipient='+15559876',
                backend='twilio',
                window_seconds=3600,
            )
            is False
        )

    @fixtures.db.user_identity(backend='other', type_='sms', identity='+15559876')
    @fixtures.db.room(
        messages=[
            {
                'content': 'twilio key',
                'meta': {
                    'type_': 'sms',
                    'backend': 'twilio',
                    'extra': {'inbound_idempotency_key': 'cross-backend'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['delivered']}
                ],
            }
        ]
    )
    @run_async
    async def test_returns_false_for_different_backend(self, room, identity):
        dao = AsyncRoomDAO()
        assert (
            await dao.check_duplicate_idempotency_key(
                'cross-backend',
                recipient='+15559876',
                backend='other',
                window_seconds=3600,
            )
            is False
        )


@use_asset('database')
class TestAsyncGetRecoverableDeliveries(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'pending',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['pending']}
                ],
            },
            {
                'content': 'retrying',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['pending', 'retrying'],
                    }
                ],
            },
            {
                'content': 'delivered',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['accepted', 'delivered'],
                    }
                ],
            },
            {
                'content': 'dead',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['retrying', 'dead_letter'],
                    }
                ],
            },
        ]
    )
    @run_async
    async def test_returns_only_pending_and_retrying(self, room):
        dao = AsyncRoomDAO()
        recoverable = await dao.get_recoverable_deliveries()

        statuses = sorted(status for _, status in recoverable)
        assert statuses == ['pending', 'retrying']


@use_asset('database')
class TestVisibilityFilter(DBIntegrationTest):
    @fixtures.db.room(
        users=[{'uuid': '00000000-0000-0000-0000-000000000001'}],
        messages=[
            {
                'content': 'sender pending',
                'user_uuid': '00000000-0000-0000-0000-000000000001',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['pending']}
                ],
            },
            {
                'content': 'other user delivered',
                'user_uuid': '00000000-0000-0000-0000-000000000002',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['accepted', 'delivered'],
                    }
                ],
            },
            {
                'content': 'other user pending',
                'user_uuid': '00000000-0000-0000-0000-000000000002',
                'meta': {'type_': 'sms', 'backend': 'twilio'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['pending'],
                    }
                ],
            },
        ],
    )
    def test_viewer_sees_own_pending_and_others_delivered(self, room):
        viewer = '00000000-0000-0000-0000-000000000001'
        messages = self._dao.room.list_messages(room, viewer_uuid=viewer)

        contents = sorted(m.content for m in messages)
        assert contents == ['other user delivered', 'sender pending']
