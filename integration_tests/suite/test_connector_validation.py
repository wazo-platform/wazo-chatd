# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

PROVIDER_UUID = uuid.uuid4()
EXTERNAL_IDENTITY = 'test:+15559876'
EXTERNAL_IDENTITY_2 = 'test:+15558765'
UNREACHABLE_IDENTITY = 'unreachable:+15559876'
INTERNAL_USER_UUID = uuid.uuid4()
RECIPIENT_USER_UUID = uuid.uuid4()


@use_asset('connectors')
class TestRoomCreationValidation(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    def test_room_with_unreachable_participant_returns_409(self, user, provider):
        self.reload_connectors()

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_from_user({
                'users': [
                    {'uuid': str(TOKEN_USER_UUID)},
                    {'uuid': str(uuid.uuid4()), 'identity': UNREACHABLE_IDENTITY},
                ],
            })

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'unreachable-participant'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    def test_room_with_reachable_external_participant_succeeds(self, user, provider):
        self.reload_connectors()

        room = self.chatd.rooms.create_from_user({
            'users': [
                {'uuid': str(TOKEN_USER_UUID)},
                {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
            ],
        })

        assert room['uuid'] is not None

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    def test_room_with_multiple_reachable_external_participants(self, user, provider):
        self.reload_connectors()

        room = self.chatd.rooms.create_from_user({
            'users': [
                {'uuid': str(TOKEN_USER_UUID)},
                {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
                {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY_2},
            ],
        })

        assert room['uuid'] is not None

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    def test_room_with_one_reachable_one_unreachable_returns_409(self, user, provider):
        self.reload_connectors()

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_from_user({
                'users': [
                    {'uuid': str(TOKEN_USER_UUID)},
                    {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
                    {'uuid': str(uuid.uuid4()), 'identity': UNREACHABLE_IDENTITY},
                ],
            })

        assert exc_info.value.status_code == 409

    def test_internal_only_room_succeeds(self):
        room = self.chatd.rooms.create_from_user({
            'users': [
                {'uuid': str(TOKEN_USER_UUID)},
                {'uuid': str(uuid.uuid4())},
            ],
        })

        assert room['uuid'] is not None


@use_asset('connectors')
class TestMessageValidation(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_external_room_without_sender_alias_uuid_returns_409(
        self, user, provider, alias, room
    ):
        self.reload_connectors()

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_message_from_user(
                str(room.uuid), {'content': 'No alias'}
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'message-alias-required'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_external_room_with_sender_alias_uuid_succeeds(
        self, user, provider, alias, room
    ):
        self.reload_connectors()

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'With alias', 'sender_alias_uuid': str(alias.uuid)},
        )

        assert message['content'] == 'With alias'

    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4()},
        ],
    )
    def test_internal_room_without_sender_alias_uuid_succeeds(self, room):
        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid), {'content': 'Internal message'}
        )

        assert message['content'] == 'Internal message'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15551234',
    )
    @fixtures.db.user_alias(
        user_uuid=RECIPIENT_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15559999',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_USER_UUID},
        ],
    )
    def test_internal_room_with_sender_alias_uuid_succeeds(
        self, user, recipient, provider, sender_alias, recipient_alias, room
    ):
        self.reload_connectors()

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Internal with alias', 'sender_alias_uuid': str(sender_alias.uuid)},
        )

        assert message['content'] == 'Internal with alias'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': INTERNAL_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_mixed_room_without_sender_alias_uuid_returns_409(
        self, user, provider, alias, room
    ):
        self.reload_connectors()

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_message_from_user(
                str(room.uuid), {'content': 'Mixed room no alias'}
            )

        assert exc_info.value.status_code == 409

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=INTERNAL_USER_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15551234',
    )
    @fixtures.db.user_alias(
        user_uuid=INTERNAL_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15558888',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': INTERNAL_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_mixed_room_with_sender_alias_uuid_succeeds(
        self, user, internal_user, provider, sender_alias, internal_alias, room
    ):
        self.reload_connectors()

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Mixed room with alias', 'sender_alias_uuid': str(sender_alias.uuid)},
        )

        assert message['content'] == 'Mixed room with alias'
