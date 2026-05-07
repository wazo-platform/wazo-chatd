# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import TOKEN_USER_UUID, ConnectorIntegrationTest, use_asset

EXTERNAL_IDENTITY = 'test:+15559876'
EXTERNAL_IDENTITY_2 = 'test:+15558765'
UNREACHABLE_IDENTITY = 'unreachable:+15559876'
INTERNAL_USER_UUID = uuid.uuid4()
RECIPIENT_USER_UUID = uuid.uuid4()


@use_asset('connectors')
class TestRoomCreationValidation(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    def test_room_with_unreachable_participant_returns_409(self, user):

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_from_user(
                {
                    'users': [
                        {'uuid': str(TOKEN_USER_UUID)},
                        {'uuid': str(uuid.uuid4()), 'identity': UNREACHABLE_IDENTITY},
                    ],
                }
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'unreachable-participant'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    def test_room_with_reachable_external_participant_succeeds(self, user, identity):

        room = self.chatd.rooms.create_from_user(
            {
                'users': [
                    {'uuid': str(TOKEN_USER_UUID)},
                    {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
                ],
            }
        )

        uuid.UUID(room['uuid'])
        assert len(room['users']) == 2

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    def test_room_with_multiple_external_participants_returns_409(self, user, identity):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_from_user(
                {
                    'users': [
                        {'uuid': str(TOKEN_USER_UUID)},
                        {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
                        {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY_2},
                    ],
                }
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'unreachable-participant'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    def test_room_with_one_reachable_one_unreachable_returns_409(self, user):

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_from_user(
                {
                    'users': [
                        {'uuid': str(TOKEN_USER_UUID)},
                        {'uuid': str(uuid.uuid4()), 'identity': EXTERNAL_IDENTITY},
                        {'uuid': str(uuid.uuid4()), 'identity': UNREACHABLE_IDENTITY},
                    ],
                }
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'unreachable-participant'

    def test_internal_only_room_succeeds(self):
        room = self.chatd.rooms.create_from_user(
            {
                'users': [
                    {'uuid': str(TOKEN_USER_UUID)},
                    {'uuid': str(uuid.uuid4())},
                ],
            }
        )

        uuid.UUID(room['uuid'])
        assert all(u.get('identity') is None for u in room['users'])


@use_asset('connectors')
class TestMessageValidation(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_external_room_without_sender_identity_uuid_returns_409(
        self, user, identity, room
    ):

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_message_from_user(
                str(room.uuid), {'content': 'No alias'}
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'message-identity-required'

        messages = self.chatd.rooms.list_messages_from_user(str(room.uuid))
        assert messages['total'] == 0

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_external_room_with_sender_identity_uuid_succeeds(
        self, user, identity, room
    ):

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'With alias', 'sender_identity_uuid': str(identity.uuid)},
        )

        assert message['content'] == 'With alias'
        assert message['delivery']['type'] == 'test'
        assert message['delivery']['backend'] == 'test'

    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4()},
        ],
    )
    def test_internal_room_without_sender_identity_uuid_succeeds(self, room):
        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid), {'content': 'Internal message'}
        )

        assert message['content'] == 'Internal message'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.user_identity(
        user_uuid=RECIPIENT_USER_UUID,
        backend='test',
        identity='test:+15559999',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_USER_UUID},
        ],
    )
    def test_internal_room_with_sender_identity_uuid_succeeds(
        self, user, recipient, sender_identity, recipient_identity, room
    ):

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {
                'content': 'Internal with alias',
                'sender_identity_uuid': str(sender_identity.uuid),
            },
        )

        assert message['content'] == 'Internal with alias'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=INTERNAL_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': INTERNAL_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_mixed_room_without_sender_identity_uuid_returns_409(
        self, user, internal_user, identity, room
    ):

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_message_from_user(
                str(room.uuid), {'content': 'Mixed room no alias'}
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'message-identity-required'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=INTERNAL_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.user_identity(
        user_uuid=INTERNAL_USER_UUID,
        backend='test',
        identity='test:+15558888',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': INTERNAL_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_mixed_room_with_sender_identity_uuid_rejects_multi_recipient(
        self, user, internal_user, sender_identity, internal_identity, room
    ):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.create_message_from_user(
                str(room.uuid),
                {
                    'content': 'Mixed room with alias',
                    'sender_identity_uuid': str(sender_identity.uuid),
                },
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'unreachable-participant'
