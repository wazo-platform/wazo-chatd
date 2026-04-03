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
UNREACHABLE_IDENTITY = 'unreachable:+15559876'


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
    def test_room_with_reachable_participant_succeeds(self, user, provider):
        self.reload_connectors()

        room = self.chatd.rooms.create_from_user({
            'users': [
                {'uuid': str(TOKEN_USER_UUID)},
                {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
            ],
        })

        assert room['uuid'] is not None

    def test_internal_room_without_connectors_succeeds(self):
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
    def test_message_without_alias_in_external_room_returns_409(
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
    def test_message_with_alias_in_external_room_succeeds(
        self, user, provider, alias, room
    ):
        self.reload_connectors()

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid), {'content': 'With alias', 'alias': 'John'}
        )

        assert message['content'] == 'With alias'
        assert message['alias'] == 'John'

    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4()},
        ],
    )
    def test_message_without_alias_in_internal_room_succeeds(self, room):
        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid), {'content': 'Internal message'}
        )

        assert message['content'] == 'Internal message'
