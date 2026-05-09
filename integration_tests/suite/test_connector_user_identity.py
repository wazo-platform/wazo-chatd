# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

USER_UUID = uuid.uuid4()


@use_asset('connectors')
class TestUserMeIdentities(ConnectorIntegrationTest):
    def test_list_empty(self):
        result = self.chatd.identities.list_from_user()

        assert result['items'] == []
        assert result['total'] == 0

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:me',
    )
    def test_list_returns_token_user_identities(self, user, identity):
        result = self.chatd.identities.list_from_user()

        assert result['total'] == 1
        assert result['items'][0]['identity'] == 'test:me'
        assert result['items'][0]['backend'] == 'test'

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:me',
    )
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:other',
    )
    def test_list_scoped_to_token_user(
        self,
        user,
        identity,
        other_user,
        other_identity,
    ):
        result = self.chatd.identities.list_from_user()

        assert result['total'] == 1
        assert result['items'][0]['identity'] == 'test:me'

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:me',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': USER_UUID, 'identity': 'test:external'},
        ],
    )
    def test_list_with_room_uuid_filters_by_reachability(self, user, identity, room):
        result = self.chatd.identities.list_from_user(room_uuid=str(room.uuid))

        assert result['total'] == 1
        assert result['items'][0]['identity'] == 'test:me'

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:me',
    )
    def test_list_with_unknown_room_uuid_returns_404(self, user, identity):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.list_from_user(room_uuid=str(uuid.uuid4()))

        assert exc_info.value.status_code == 404

    def test_list_with_invalid_room_uuid_returns_400(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.list_from_user(room_uuid='not-a-uuid')

        assert exc_info.value.status_code == 400

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:me',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:recipient',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': USER_UUID},
        ],
    )
    def test_list_with_room_uuid_wazo_user_recipient(
        self, me, recipient, my_identity, recipient_identity, room
    ):
        result = self.chatd.identities.list_from_user(room_uuid=str(room.uuid))

        assert result['total'] == 1
        assert result['items'][0]['identity'] == 'test:me'

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': USER_UUID},
        ],
    )
    def test_list_with_room_uuid_internal_only_returns_empty(self, me, recipient, room):
        result = self.chatd.identities.list_from_user(room_uuid=str(room.uuid))

        assert result['total'] == 0
        assert result['items'] == []
