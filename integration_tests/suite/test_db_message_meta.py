# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for MessageMeta and DeliveryRecord models."""

from __future__ import annotations

import pytest

from wazo_chatd.database.models import DeliveryRecord, MessageMeta, Room, RoomMessage
from wazo_chatd.database.queries.async_.room import AsyncRoomDAO
from wazo_chatd.exceptions import DuplicateExternalIdException

from .helpers import fixtures
from .helpers.async_ import run_async
from .helpers.base import DBIntegrationTest, use_asset


def _build_message(room: Room, *, backend: str, external_id: str | None) -> RoomMessage:
    sender = room.users[0]
    return RoomMessage(
        content='hello',
        user_uuid=sender.uuid,
        tenant_uuid=room.tenant_uuid,
        wazo_uuid=sender.wazo_uuid,
        meta=MessageMeta(backend=backend, external_id=external_id),
    )


@use_asset('database')
class TestMessageMeta(DBIntegrationTest):
    @fixtures.db.room(messages=[{'content': 'hello'}])
    def test_message_meta_created_with_message(self, room):
        message = room.messages[0]

        meta = MessageMeta(
            message_uuid=message.uuid,
            type_='sms',
            backend='twilio',
        )
        self._session.add(meta)
        self._session.flush()

        self._session.refresh(message)
        assert message.meta is not None
        assert message.meta.type_ == 'sms'
        assert message.meta.backend == 'twilio'

    @fixtures.db.room(messages=[{'content': 'internal msg'}])
    def test_message_without_meta(self, room):
        message = room.messages[0]
        assert message.meta is None

    @fixtures.db.room(messages=[{'content': 'tracked'}])
    def test_meta_with_delivery_records(self, room):
        message = room.messages[0]

        meta = MessageMeta(
            message_uuid=message.uuid,
            type_='sms',
            backend='twilio',
        )
        self._session.add(meta)
        self._session.flush()

        record_1 = DeliveryRecord(
            message_uuid=message.uuid,
            status='pending',
        )
        record_2 = DeliveryRecord(
            message_uuid=message.uuid,
            status='accepted',
        )
        record_3 = DeliveryRecord(
            message_uuid=message.uuid,
            status='sent',
        )
        self._session.add_all([record_1, record_2, record_3])
        self._session.flush()

        self._session.refresh(meta)
        assert len(meta.records) == 3
        assert meta.status == 'sent'

    @fixtures.db.room(messages=[{'content': 'fail'}])
    def test_meta_with_failed_delivery(self, room):
        message = room.messages[0]

        meta = MessageMeta(
            message_uuid=message.uuid,
            type_='sms',
            backend='twilio',
            retry_count=3,
        )
        self._session.add(meta)
        self._session.flush()

        record = DeliveryRecord(
            message_uuid=message.uuid,
            status='dead_letter',
            reason='Max retries exceeded',
        )
        self._session.add(record)
        self._session.flush()

        self._session.refresh(meta)
        assert meta.status == 'dead_letter'
        assert meta.records[0].reason == 'Max retries exceeded'

    @fixtures.db.room(users=[{}])
    @run_async
    async def test_external_id_unique_per_backend(self, room):
        dao = AsyncRoomDAO()
        first = _build_message(room, backend='twilio', external_id='SM_DUP_1')
        await dao.add_message(room, first)

        second = _build_message(room, backend='twilio', external_id='SM_DUP_1')
        with pytest.raises(DuplicateExternalIdException):
            await dao.add_message(room, second)

    @fixtures.db.room(users=[{}])
    @run_async
    async def test_external_id_can_repeat_across_backends(self, room):
        dao = AsyncRoomDAO()
        first = _build_message(room, backend='twilio', external_id='SM_REUSED')
        second = _build_message(room, backend='vonage', external_id='SM_REUSED')
        await dao.add_message(room, first)
        await dao.add_message(room, second)

    @fixtures.db.room(users=[{}])
    @run_async
    async def test_external_id_null_repeats_allowed(self, room):
        dao = AsyncRoomDAO()
        first = _build_message(room, backend='twilio', external_id=None)
        second = _build_message(room, backend='twilio', external_id=None)
        await dao.add_message(room, first)
        await dao.add_message(room, second)

    @fixtures.db.room(messages=[{'content': 'extra data'}])
    def test_meta_extra_jsonb(self, room):
        message = room.messages[0]

        meta = MessageMeta(
            message_uuid=message.uuid,
            backend='twilio',
            extra={
                'idempotency_key': 'idem-123',
                'account_sid': 'AC123',
            },
        )
        self._session.add(meta)
        self._session.flush()

        self._session.refresh(meta)
        assert meta.extra['idempotency_key'] == 'idem-123'
        assert meta.extra['account_sid'] == 'AC123'


@use_asset('database')
class TestCascadeDeletes(DBIntegrationTest):
    @fixtures.db.room(messages=[{'content': 'cascade test'}])
    def test_delete_room_cascades_to_meta_and_records(self, room):
        message = room.messages[0]

        meta = MessageMeta(
            message_uuid=message.uuid,
            type_='sms',
            backend='twilio',
        )
        self._session.add(meta)
        self._session.flush()

        record = DeliveryRecord(
            message_uuid=message.uuid,
            status='accepted',
        )
        self._session.add(record)
        self._session.flush()

        message_uuid = message.uuid

        # Delete the room — should cascade to message → meta → records
        self._session.query(Room).filter(Room.uuid == room.uuid).delete()
        self._session.flush()

        assert (
            self._session.query(MessageMeta)
            .filter(MessageMeta.message_uuid == message_uuid)
            .first()
            is None
        )

        assert (
            self._session.query(DeliveryRecord)
            .filter(DeliveryRecord.message_uuid == message_uuid)
            .first()
            is None
        )
