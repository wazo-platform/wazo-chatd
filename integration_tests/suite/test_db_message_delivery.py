# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for room/message-delivery DAO methods."""

from __future__ import annotations

import pytest

from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageDelivery,
    MessageMeta,
    Room,
    RoomMessage,
    RoomUser,
)
from wazo_chatd.exceptions import DuplicateExternalIdException

from .helpers import fixtures
from .helpers.async_ import run_async
from .helpers.base import TOKEN_TENANT_UUID as TENANT_1
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
class TestAsyncAddMessage(DBIntegrationTest):
    @fixtures.db.room(users=[{}])
    @run_async
    async def test_duplicate_external_id_raises(self, room):
        await self._async_dao.room.add_message(
            room, _build_message(room, backend='sms_backend', external_id='SM_DUP_1')
        )
        with pytest.raises(DuplicateExternalIdException):
            await self._async_dao.room.add_message(
                room,
                _build_message(room, backend='sms_backend', external_id='SM_DUP_1'),
            )


@use_asset('database')
class TestAddMessage(DBIntegrationTest):
    @fixtures.db.room(users=[{}])
    def test_null_external_id_repeats_allowed(self, room):
        message_1 = _build_message(
            room,
            backend='sms_backend',
            external_id=None,
            recipient_identity='+15559876',
        )
        message_2 = _build_message(
            room,
            backend='sms_backend',
            external_id=None,
            recipient_identity='+15558888',
        )

        self._dao.room.add_message(room, message_1)
        self._dao.room.add_message(room, message_2)

        self._session.refresh(message_1)
        self._session.refresh(message_2)

        deliveries = [*message_1.meta.deliveries, *message_2.meta.deliveries]
        assert len(deliveries) == 2
        assert all(d.external_id is None for d in deliveries)


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
            backend='sms_backend',
            type_='sms',
        )
        self._dao.room.add_message(room, message)

        self._session.refresh(message)
        assert message.meta is not None
        assert message.meta.backend == 'sms_backend'
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
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
        result = self._dao.room.find_tenant_by_external_id('SM_LOOKUP', 'sms_backend')
        assert result == str(room.tenant_uuid)

    @fixtures.db.room(messages=[{'content': 'no external'}])
    def test_returns_none_when_not_found(self, room):
        assert (
            self._dao.room.find_tenant_by_external_id('SM_MISSING', 'sms_backend')
            is None
        )


@use_asset('database')
class TestAsyncGetMessageMetaByExternalId(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'looked up',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
        meta = await self._async_dao.room.get_message_meta_by_external_id(
            'SM_FETCH', 'sms_backend'
        )

        assert meta is not None
        assert meta.backend == 'sms_backend'
        assert len(meta.deliveries) == 1
        assert meta.deliveries[0].external_id == 'SM_FETCH'

    @fixtures.db.room(messages=[{'content': 'no meta'}])
    @run_async
    async def test_returns_none_when_external_id_not_found(self, room):
        assert (
            await self._async_dao.room.get_message_meta_by_external_id(
                'SM_MISSING', 'sms_backend'
            )
            is None
        )


@use_asset('database')
class TestAsyncListPendingExternalIds(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'pending msg',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
                'meta': {'type_': 'sms', 'backend': 'sms_alt_backend'},
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
        result = await self._async_dao.room.list_pending_external_ids(
            tenant_uuid=str(room.tenant_uuid), backend='sms_backend'
        )

        assert result == ['SM_PENDING']


@use_asset('database')
class TestAsyncAddDeliveryRecord(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'tracked',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['pending']}
                ],
            }
        ]
    )
    @run_async
    async def test_record_anchored_to_delivery(self, room):
        delivery = room.messages[0].meta.deliveries[0]

        record = await self._async_dao.room.add_delivery_record(
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
                    'backend': 'sms_backend',
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
        meta = await self._async_dao.room.find_matching_signature(
            str(room.uuid), 'sig-abc'
        )
        assert meta is not None
        assert meta.message_uuid == room.messages[0].uuid

    @fixtures.db.room(
        messages=[
            {
                'content': 'no match',
                'meta': {
                    'type_': 'sms',
                    'backend': 'sms_backend',
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
        assert (
            await self._async_dao.room.find_matching_signature(
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
                    'backend': 'sms_backend',
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
        assert (
            await self._async_dao.room.find_matching_signature(
                str(room_b.uuid), 'sig-abc'
            )
            is None
        )


@use_asset('database')
class TestAsyncCheckDuplicateIdempotencyKey(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'with key',
                'meta': {
                    'type_': 'sms',
                    'backend': 'sms_backend',
                    'extra': {'inbound_idempotency_key': 'idem-123'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['delivered']}
                ],
            }
        ]
    )
    @fixtures.db.user_identity(backend='sms_backend', type_='sms', identity='+15559876')
    @run_async
    async def test_returns_true_when_key_present(self, room, identity):
        assert (
            await self._async_dao.room.check_duplicate_idempotency_key(
                'idem-123',
                recipient='+15559876',
                backend='sms_backend',
                message_type='sms',
                window_seconds=3600,
            )
            is True
        )

    @fixtures.db.room(messages=[{'content': 'no key'}])
    @fixtures.db.user_identity(backend='sms_backend', type_='sms', identity='+15559876')
    @run_async
    async def test_returns_false_when_key_absent(self, room, identity):
        assert (
            await self._async_dao.room.check_duplicate_idempotency_key(
                'idem-missing',
                recipient='+15559876',
                backend='sms_backend',
                message_type='sms',
                window_seconds=3600,
            )
            is False
        )

    @fixtures.db.room(
        messages=[
            {
                'content': 'sms key',
                'meta': {
                    'type_': 'sms',
                    'backend': 'sms_backend',
                    'extra': {'inbound_idempotency_key': 'cross-backend'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['delivered']}
                ],
            }
        ]
    )
    @fixtures.db.user_identity(backend='other', type_='sms', identity='+15559876')
    @run_async
    async def test_returns_false_for_different_backend(self, room, identity):
        assert (
            await self._async_dao.room.check_duplicate_idempotency_key(
                'cross-backend',
                recipient='+15559876',
                backend='other',
                message_type='sms',
                window_seconds=3600,
            )
            is False
        )

    @fixtures.db.room(
        messages=[
            {
                'content': 'sms key',
                'meta': {
                    'type_': 'sms',
                    'backend': 'sms_backend',
                    'extra': {'inbound_idempotency_key': 'multi-type'},
                },
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['delivered']}
                ],
            }
        ]
    )
    @fixtures.db.user_identity(
        backend='sms_backend', type_='whatsapp', identity='+15559876'
    )
    @fixtures.db.user_identity(backend='sms_backend', type_='sms', identity='+15559876')
    @run_async
    async def test_returns_true_with_matching_message_type(
        self, room, sms_identity, whatsapp_identity
    ):
        assert (
            await self._async_dao.room.check_duplicate_idempotency_key(
                'multi-type',
                recipient='+15559876',
                backend='sms_backend',
                message_type='sms',
                window_seconds=3600,
            )
            is True
        )


@use_asset('database')
class TestAsyncGetRecoverableDeliveries(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'pending',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['pending']}
                ],
            },
            {
                'content': 'retrying',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['pending', 'retrying'],
                    }
                ],
            },
            {
                'content': 'delivered',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'statuses': ['accepted', 'delivered'],
                    }
                ],
            },
            {
                'content': 'dead',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
        recoverable = await self._async_dao.room.get_recoverable_deliveries()

        statuses = sorted(status for _, status in recoverable)
        assert statuses == ['pending', 'retrying']


@use_asset('database')
class TestAsyncGetMessageDelivery(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'has delivery',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_GET',
                        'statuses': ['pending'],
                    }
                ],
            }
        ],
    )
    @run_async
    async def test_returns_delivery_with_records_eagerly_loaded(self, room):
        meta = await self._async_dao.room.get_message_meta_by_external_id(
            'SM_GET', 'sms_backend'
        )
        assert meta is not None
        delivery_id = meta.deliveries[0].id

        delivery = await self._async_dao.room.get_message_delivery(delivery_id)

        assert delivery is not None
        assert delivery.external_id == 'SM_GET'
        assert len(delivery.records) == 1
        assert delivery.records[0].status == 'pending'

    @run_async
    async def test_returns_none_when_unknown_id(self):
        delivery = await self._async_dao.room.get_message_delivery(999_999)

        assert delivery is None


@use_asset('database')
class TestAsyncGetMessageMeta(DBIntegrationTest):
    @fixtures.db.room(
        messages=[
            {
                'content': 'meta target',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_META_GET',
                        'statuses': ['pending'],
                    }
                ],
            }
        ],
    )
    @run_async
    async def test_returns_meta_with_eagerly_loaded_relations(self, room):
        message_uuid = room.messages[0].uuid

        meta = await self._async_dao.room.get_message_meta(str(message_uuid))

        assert meta is not None
        assert meta.backend == 'sms_backend'
        assert meta.message.content == 'meta target'
        assert len(meta.deliveries) == 1
        assert meta.deliveries[0].records[0].status == 'pending'

    @run_async
    async def test_returns_none_when_unknown_message(self):
        unknown = '00000000-0000-0000-0000-000000000999'

        assert await self._async_dao.room.get_message_meta(unknown) is None


@use_asset('database')
class TestAsyncCreateRoom(DBIntegrationTest):
    @run_async
    async def test_creates_room_with_participants(self):
        participants = [
            RoomUser(uuid='00000000-0000-0000-0000-000000000001'),
            RoomUser(uuid='00000000-0000-0000-0000-000000000002'),
        ]

        room = await self._async_dao.room.create_room(str(TENANT_1), participants)

        assert room.uuid is not None
        assert str(room.tenant_uuid) == str(TENANT_1)
        assert {str(u.uuid) for u in room.users} == {
            '00000000-0000-0000-0000-000000000001',
            '00000000-0000-0000-0000-000000000002',
        }


@use_asset('database')
class TestAsyncAddMessageMeta(DBIntegrationTest):
    @fixtures.db.room(
        users=[{}],
        messages=[{'content': 'no meta yet'}],
    )
    @run_async
    async def test_adds_meta_and_initial_record(self, room):
        message = room.messages[0]

        delivery = MessageDelivery(
            recipient_identity='+15559876',
            backend='sms_backend',
            type_='sms',
        )
        meta = MessageMeta(
            message_uuid=message.uuid,
            type_='sms',
            backend='sms_backend',
            deliveries=[delivery],
        )
        initial_record = DeliveryRecord(delivery=delivery, status='pending')

        result = await self._async_dao.room.add_message_meta(meta, initial_record)

        assert result.message_uuid == message.uuid
        refreshed = await self._async_dao.room.get_message_meta(str(message.uuid))
        assert refreshed is not None
        assert refreshed.backend == 'sms_backend'
        assert len(refreshed.deliveries) == 1
        assert refreshed.deliveries[0].records[0].status == 'pending'


@use_asset('database')
class TestAsyncFindRoom(DBIntegrationTest):
    @fixtures.db.room(users=[{'uuid': '00000000-0000-0000-0000-000000000aaa'}])
    @run_async
    async def test_returns_room_with_exact_participants(self, room):
        participants = [RoomUser(uuid='00000000-0000-0000-0000-000000000aaa')]

        result = await self._async_dao.room.find_room(
            str(room.tenant_uuid), participants
        )

        assert result is not None
        assert result.uuid == room.uuid

    @fixtures.db.room(users=[{'uuid': '00000000-0000-0000-0000-000000000aaa'}])
    @run_async
    async def test_returns_none_when_participants_differ(self, room):
        participants = [RoomUser(uuid='00000000-0000-0000-0000-000000000bbb')]

        result = await self._async_dao.room.find_room(
            str(room.tenant_uuid), participants
        )

        assert result is None


@use_asset('database')
class TestAsyncUpdateMessageMeta(DBIntegrationTest):
    @fixtures.db.room(
        users=[{}],
        messages=[
            {
                'content': 'updatable',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {
                        'recipient_identity': '+15559876',
                        'external_id': 'SM_UPDATABLE',
                        'statuses': ['accepted'],
                    }
                ],
            }
        ],
    )
    @run_async
    async def test_persists_modified_extra(self, room):
        meta = await self._async_dao.room.get_message_meta_by_external_id(
            'SM_UPDATABLE', 'sms_backend'
        )
        assert meta is not None

        meta.extra = {'reviewed': True}  # type: ignore[assignment]
        await self._async_dao.room.update_message_meta(meta)

        refreshed = await self._async_dao.room.get_message_meta_by_external_id(
            'SM_UPDATABLE', 'sms_backend'
        )
        assert refreshed is not None
        assert refreshed.extra == {'reviewed': True}


@use_asset('database')
class TestListMessagesVisibility(DBIntegrationTest):
    @fixtures.db.room(
        users=[{'uuid': '00000000-0000-0000-0000-000000000001'}],
        messages=[
            {
                'content': 'sender pending',
                'user_uuid': '00000000-0000-0000-0000-000000000001',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
                'deliveries': [
                    {'recipient_identity': '+15559876', 'statuses': ['pending']}
                ],
            },
            {
                'content': 'other user delivered',
                'user_uuid': '00000000-0000-0000-0000-000000000002',
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
                'meta': {'type_': 'sms', 'backend': 'sms_backend'},
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
