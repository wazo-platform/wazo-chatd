# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests for connector database models.

Tests ChatProvider, UserAlias, MessageMeta, DeliveryRecord models
and their relationships using direct DB access.

TODO: Once wazo-confd-mock (in wazo-test-helpers) supports
``chat_provider`` and ``user_alias`` response types, add API-level
integration tests that use the confd mock instead of direct DB
fixtures. The current direct-DB approach is a workaround.
"""

from __future__ import annotations

import uuid

from wazo_chatd.database.models import (
    ChatProvider,
    DeliveryRecord,
    MessageMeta,
    Room,
    RoomUser,
    UserAlias,
)

from .helpers import fixtures
from .helpers.base import TOKEN_TENANT_UUID as TENANT_1
from .helpers.base import WAZO_UUID, DBIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()
USER_UUID_2 = uuid.uuid4()


@use_asset('database')
class TestChatProvider(DBIntegrationTest):
    @fixtures.db.chat_provider(name='Twilio SMS', type_='sms', backend='twilio')
    def test_create_provider(self, provider):
        result = (
            self._session.query(ChatProvider)
            .filter(ChatProvider.uuid == provider.uuid)
            .first()
        )

        assert result is not None
        assert result.name == 'Twilio SMS'
        assert result.type_ == 'sms'
        assert result.backend == 'twilio'
        assert result.tenant_uuid == TENANT_1

    @fixtures.db.chat_provider(name='Provider A', type_='sms', backend='twilio')
    @fixtures.db.chat_provider(name='Provider B', type_='whatsapp', backend='twilio')
    def test_multiple_providers_same_backend(self, provider_b, provider_a):
        results = (
            self._session.query(ChatProvider)
            .filter(ChatProvider.backend == 'twilio')
            .all()
        )

        assert len(results) == 2

    @fixtures.db.chat_provider(
        configuration={'account_sid': 'AC123', 'auth_token': 'secret'},
    )
    def test_provider_configuration_jsonb(self, provider):
        result = (
            self._session.query(ChatProvider)
            .filter(ChatProvider.uuid == provider.uuid)
            .first()
        )

        assert result.configuration['account_sid'] == 'AC123'
        assert result.configuration['auth_token'] == 'secret'


@use_asset('database')
class TestUserAlias(DBIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.chat_provider(name='Twilio SMS')
    def test_create_alias(self, provider, user):
        alias = UserAlias(
            tenant_uuid=TENANT_1,
            user_uuid=user.uuid,
            provider_uuid=provider.uuid,
            identity='+15551234567',
        )
        self._session.add(alias)
        self._session.flush()

        result = (
            self._session.query(UserAlias)
            .filter(UserAlias.identity == '+15551234567')
            .first()
        )

        assert result is not None
        assert result.user_uuid == user.uuid
        assert result.provider_uuid == provider.uuid

        # cleanup
        self._session.delete(result)
        self._session.flush()

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.chat_provider(name='Twilio SMS')
    @fixtures.db.chat_provider(name='Vonage SMS', backend='vonage')
    def test_user_multiple_aliases(self, provider_vonage, provider_twilio, user):
        alias_1 = UserAlias(
            tenant_uuid=TENANT_1,
            user_uuid=user.uuid,
            provider_uuid=provider_twilio.uuid,
            identity='+15551111111',
        )
        alias_2 = UserAlias(
            tenant_uuid=TENANT_1,
            user_uuid=user.uuid,
            provider_uuid=provider_vonage.uuid,
            identity='+15552222222',
        )
        self._session.add_all([alias_1, alias_2])
        self._session.flush()

        results = (
            self._session.query(UserAlias)
            .filter(UserAlias.user_uuid == user.uuid)
            .all()
        )

        assert len(results) == 2

        # cleanup
        for alias in results:
            self._session.delete(alias)
        self._session.flush()


@use_asset('database')
class TestRoomUserIdentity(DBIntegrationTest):
    @fixtures.db.room(
        users=[
            {'uuid': USER_UUID_1},
            {'uuid': USER_UUID_2, 'identity': '+15559876543'},
        ],
    )
    def test_room_with_external_participant(self, room):
        internal_user = next(u for u in room.users if u.uuid == USER_UUID_1)
        external_user = next(u for u in room.users if u.uuid == USER_UUID_2)

        assert internal_user.identity is None
        assert external_user.identity == '+15559876543'

    @fixtures.db.room(
        users=[
            {'uuid': USER_UUID_1},
            {'uuid': USER_UUID_2},
        ],
    )
    def test_room_all_internal(self, room):
        for user in room.users:
            assert user.identity is None

    def test_query_by_identity(self):
        ext_uuid = uuid.uuid4()
        room = Room(tenant_uuid=TENANT_1)
        room.users = [
            RoomUser(
                uuid=ext_uuid,
                tenant_uuid=TENANT_1,
                wazo_uuid=WAZO_UUID,
                identity='+15559999999',
            ),
        ]
        self._session.add(room)
        self._session.flush()

        results = (
            self._session.query(RoomUser)
            .filter(RoomUser.identity == '+15559999999')
            .all()
        )

        assert len(results) == 1
        assert results[0].uuid == ext_uuid

        # cleanup
        self._session.query(Room).filter(Room.uuid == room.uuid).delete()
        self._session.commit()


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
            status='sending',
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
            status='sent',
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
