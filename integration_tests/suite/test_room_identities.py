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

RECIPIENT_UUID = uuid.uuid4()
EXTERNAL_IDENTITY = 'test:+15559876'
SENDER_IDENTITY = 'test:+15551234'


@use_asset('connectors')
class TestRoomIdentities(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_UUID, 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_external_participant_returns_sender_identities(
        self, sender, recipient, identity, room
    ):
        result = self.chatd.rooms.list_available_identities_from_user(
            str(room.uuid)
        )

        assert result['total'] >= 1
        identities = [item['identity'] for item in result['items']]
        assert SENDER_IDENTITY in identities

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.user_identity(
        user_uuid=RECIPIENT_UUID,
        backend='test',
        identity='test:+15557777',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_UUID},
        ],
    )
    def test_wazo_user_with_identity_returns_sender_identities(
        self, sender, recipient, sender_identity, recipient_identity, room
    ):
        result = self.chatd.rooms.list_available_identities_from_user(
            str(room.uuid)
        )

        assert result['total'] >= 1
        identities = [item['identity'] for item in result['items']]
        assert SENDER_IDENTITY in identities

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_UUID)
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_UUID},
        ],
    )
    def test_internal_only_room_returns_empty(self, sender, recipient, room):
        result = self.chatd.rooms.list_available_identities_from_user(
            str(room.uuid)
        )

        assert result['total'] == 0
        assert result['items'] == []

    def test_unknown_room_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.rooms.list_available_identities_from_user(
                str(uuid.uuid4())
            )

        assert exc_info.value.status_code == 404
