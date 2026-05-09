# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    TOKEN_SUBTENANT_UUID,
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

USER_UUID = uuid.uuid4()
USER_A_UUID = uuid.uuid4()
USER_B_UUID = uuid.uuid4()
SUBTENANT_USER_UUID = uuid.uuid4()


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


@use_asset('connectors')
class TestIdentityList(ConnectorIntegrationTest):
    def test_list_empty(self):
        result = self.chatd.identities.list()

        assert result['items'] == []
        assert result['total'] == 0

    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:a',
    )
    @fixtures.db.user(uuid=USER_B_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_B_UUID,
        backend='test',
        type_='test',
        identity='test:b',
    )
    def test_list_returns_all_identities_in_tenant(
        self, user_a, identity_a, user_b, identity_b
    ):
        result = self.chatd.identities.list()

        assert result['total'] == 2
        identities = sorted(result['items'], key=lambda i: i['identity'])
        assert identities[0]['identity'] == 'test:a'
        assert identities[1]['identity'] == 'test:b'

    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:owner',
    )
    def test_list_response_includes_owner_fields(self, user, identity):
        result = self.chatd.identities.list()

        assert result['total'] == 1
        item = result['items'][0]
        assert item['user_uuid'] == str(USER_A_UUID)
        assert item['tenant_uuid'] == str(TOKEN_TENANT_UUID)

    @fixtures.db.user(uuid=USER_A_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:parent',
    )
    @fixtures.db.user(uuid=SUBTENANT_USER_UUID, tenant_uuid=TOKEN_SUBTENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=SUBTENANT_USER_UUID,
        tenant_uuid=TOKEN_SUBTENANT_UUID,
        backend='test',
        type_='test',
        identity='test:subtenant',
    )
    def test_list_subtenant_token_sees_only_its_tenant(
        self, parent_user, parent_identity, sub_user, sub_identity
    ):
        chatd = self.make_user_chatd(SUBTENANT_USER_UUID, TOKEN_SUBTENANT_UUID)

        result = chatd.identities.list(tenant_uuid=str(TOKEN_SUBTENANT_UUID))

        assert result['total'] == 1
        assert result['items'][0]['identity'] == 'test:subtenant'


@use_asset('connectors')
class TestIdentityItem(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:item',
    )
    def test_get(self, user, identity):
        result = self.chatd.identities.get(str(identity.uuid))

        assert result['uuid'] == str(identity.uuid)
        assert result['identity'] == 'test:item'
        assert result['user_uuid'] == str(USER_A_UUID)
        assert result['tenant_uuid'] == str(TOKEN_TENANT_UUID)

    def test_get_unknown_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.get(str(uuid.uuid4()))

        assert exc_info.value.status_code == 404


@use_asset('connectors')
class TestIdentityCreate(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_A_UUID)
    def test_create(self, user):
        result = self.chatd.identities.create(
            {
                'user_uuid': str(USER_A_UUID),
                'backend': 'test',
                'type': 'test',
                'identity': 'test:create',
            }
        )

        assert result['user_uuid'] == str(USER_A_UUID)
        assert result['tenant_uuid'] == str(TOKEN_TENANT_UUID)
        assert result['backend'] == 'test'
        assert result['type'] == 'test'
        assert result['identity'] == 'test:create'
        uuid.UUID(result['uuid'])

    def test_create_unknown_user_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.create(
                {
                    'user_uuid': str(uuid.uuid4()),
                    'backend': 'test',
                    'type': 'test',
                    'identity': 'test:nouser',
                }
            )

        assert exc_info.value.status_code == 404

    @fixtures.db.user(uuid=USER_A_UUID)
    def test_create_unknown_backend_returns_400(self, user):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.create(
                {
                    'user_uuid': str(USER_A_UUID),
                    'backend': 'nonexistent-backend',
                    'type': 'test',
                    'identity': 'test:badbackend',
                }
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_id == 'unknown-backend'

    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:dup',
    )
    def test_create_duplicate_identity_returns_409(self, user, identity):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.create(
                {
                    'user_uuid': str(USER_A_UUID),
                    'backend': 'test',
                    'type': 'test',
                    'identity': 'test:dup',
                }
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.error_id == 'duplicate-identity'


@use_asset('connectors')
class TestIdentityUpdate(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:original',
    )
    def test_update_identity_value(self, user, identity):
        self.chatd.identities.update(
            str(identity.uuid),
            {'identity': 'test:updated'},
        )

        persisted = self.chatd.identities.get(str(identity.uuid))
        assert persisted['identity'] == 'test:updated'

    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user(uuid=USER_B_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:reassign',
    )
    def test_update_reassigns_user(self, user_a, user_b, identity):
        self.chatd.identities.update(
            str(identity.uuid),
            {'user_uuid': str(USER_B_UUID)},
        )

        persisted = self.chatd.identities.get(str(identity.uuid))
        assert persisted['user_uuid'] == str(USER_B_UUID)
        assert persisted['identity'] == 'test:reassign'

    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:reassign-unknown',
    )
    def test_update_reassign_to_unknown_user_returns_404(self, user, identity):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.update(
                str(identity.uuid),
                {'user_uuid': str(uuid.uuid4())},
            )

        assert exc_info.value.status_code == 404

    def test_update_unknown_identity_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.update(
                str(uuid.uuid4()),
                {'identity': 'test:foo'},
            )

        assert exc_info.value.status_code == 404


@use_asset('connectors')
class TestIdentityDelete(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_A_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_A_UUID,
        backend='test',
        type_='test',
        identity='test:delete',
    )
    def test_delete(self, user, identity):
        identity_uuid = str(identity.uuid)

        self.chatd.identities.delete(identity_uuid)

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.get(identity_uuid)
        assert exc_info.value.status_code == 404

    def test_delete_unknown_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.identities.delete(str(uuid.uuid4()))

        assert exc_info.value.status_code == 404


@use_asset('connectors')
class TestIdentityAuth(ConnectorIntegrationTest):
    @pytest.mark.parametrize('bad_token', ['', str(uuid.uuid4())])
    def test_missing_or_invalid_token_returns_401(self, bad_token):
        chatd = self.asset_cls.make_chatd(token=bad_token)

        with pytest.raises(ChatdError) as exc_info:
            chatd.identities.list()

        assert exc_info.value.status_code == 401
