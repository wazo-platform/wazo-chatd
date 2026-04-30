# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import TOKEN_SUBTENANT_UUID as OTHER_TENANT_UUID
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

USER_UUID = uuid.uuid4()
OTHER_TENANT_USER_UUID = uuid.uuid4()


@use_asset('connectors')
class TestUserIdentityCRUD(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID)
    def test_list_empty(self, user):
        result = self.chatd.user_identities.list(str(USER_UUID))

        assert result['items'] == []
        assert result['total'] == 0

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_list_returns_identities(self, user, identity):
        result = self.chatd.user_identities.list(str(USER_UUID))

        assert result['total'] == 1
        assert result['items'][0]['backend'] == 'twilio'
        assert result['items'][0]['type'] == 'sms'
        assert result['items'][0]['identity'] == '+15551234567'

    @fixtures.db.user(uuid=USER_UUID)
    def test_create(self, user):
        result = self.chatd.user_identities.create(
            str(USER_UUID),
            {'backend': 'test', 'type': 'test', 'identity': 'test:create'},
        )

        assert result['backend'] == 'test'
        assert result['type'] == 'test'
        assert result['identity'] == 'test:create'
        assert 'uuid' in result

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_with_extra(self, user):
        result = self.chatd.user_identities.create(
            str(USER_UUID),
            {
                'backend': 'test',
                'type': 'test',
                'identity': 'test:extra',
                'extra': {'account_sid': 'AC123'},
            },
        )

        assert result['type'] == 'test'
        assert result['extra'] == {'account_sid': 'AC123'}

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_unknown_backend_returns_400(self, user):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.create(
                str(USER_UUID),
                {
                    'backend': 'nonexistent-backend',
                    'type': 'sms',
                    'identity': '+15551112222',
                },
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_id == 'unknown-backend'

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_missing_backend_returns_400(self, user):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.create(
                str(USER_UUID),
                {'type': 'sms', 'identity': '+15557777777'},
            )

        assert exc_info.value.status_code == 400

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_missing_identity_returns_400(self, user):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.create(
                str(USER_UUID),
                {'backend': 'twilio', 'type': 'sms'},
            )

        assert exc_info.value.status_code == 400

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_get(self, user, identity):
        result = self.chatd.user_identities.get(str(USER_UUID), str(identity.uuid))

        assert result['uuid'] == str(identity.uuid)
        assert result['backend'] == 'twilio'
        assert result['type'] == 'sms'
        assert result['identity'] == '+15551234567'

    @fixtures.db.user(uuid=USER_UUID)
    def test_get_unknown_returns_404(self, user):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.get(str(USER_UUID), str(uuid.uuid4()))

        assert exc_info.value.status_code == 404

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='test',
        type_='test',
        identity='test:original',
    )
    def test_update(self, user, identity):
        self.chatd.user_identities.update(
            str(USER_UUID),
            str(identity.uuid),
            {'backend': 'test', 'type': 'test', 'identity': 'test:updated'},
        )

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_delete(self, user, identity):
        identity_uuid = str(identity.uuid)

        self.chatd.user_identities.delete(str(USER_UUID), identity_uuid)

        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.get(str(USER_UUID), identity_uuid)

        assert exc_info.value.status_code == 404

    @fixtures.db.user(uuid=USER_UUID)
    def test_delete_unknown_returns_404(self, user):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.delete(str(USER_UUID), str(uuid.uuid4()))

        assert exc_info.value.status_code == 404


@use_asset('connectors')
class TestUserIdentityAuth(ConnectorIntegrationTest):
    def test_no_token_returns_401(self):
        chatd = self.asset_cls.make_chatd(token='')

        with pytest.raises(ChatdError) as exc_info:
            chatd.user_identities.list(str(USER_UUID))

        assert exc_info.value.status_code == 401

    def test_invalid_token_returns_401(self):
        chatd = self.asset_cls.make_chatd(token=str(uuid.uuid4()))

        with pytest.raises(ChatdError) as exc_info:
            chatd.user_identities.list(str(USER_UUID))

        assert exc_info.value.status_code == 401

    @fixtures.db.user(uuid=OTHER_TENANT_USER_UUID, tenant_uuid=OTHER_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=OTHER_TENANT_USER_UUID,
        tenant_uuid=OTHER_TENANT_UUID,
        backend='twilio',
        type_='sms',
        identity='+15553334444',
    )
    def test_token_sees_own_tenant_identities(self, user, identity):
        token = self.asset_cls.create_user_token(
            str(OTHER_TENANT_USER_UUID), str(OTHER_TENANT_UUID)
        )
        chatd = self.asset_cls.make_chatd(token=token)

        result = chatd.user_identities.list(
            str(OTHER_TENANT_USER_UUID), tenant_uuid=str(OTHER_TENANT_UUID)
        )

        assert result['total'] == 1
        assert result['items'][0]['identity'] == '+15553334444'

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551112222',
    )
    def test_user_identity_tenant_isolation(self, user, identity):
        other_token = self.asset_cls.create_user_token(
            str(OTHER_TENANT_USER_UUID), str(OTHER_TENANT_UUID)
        )
        chatd = self.asset_cls.make_chatd(token=other_token)

        with pytest.raises(ChatdError) as exc_info:
            chatd.user_identities.list(
                str(USER_UUID), tenant_uuid=str(TOKEN_TENANT_UUID)
            )

        assert exc_info.value.status_code == 401


@use_asset('connectors')
class TestUserMeIdentities(ConnectorIntegrationTest):
    def test_list_empty(self):
        result = self.chatd.user_identities.list_from_user()

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
        result = self.chatd.user_identities.list_from_user()

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
        result = self.chatd.user_identities.list_from_user()

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
        result = self.chatd.user_identities.list_from_user(room_uuid=str(room.uuid))

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
            self.chatd.user_identities.list_from_user(room_uuid=str(uuid.uuid4()))

        assert exc_info.value.status_code == 404

    def test_list_with_invalid_room_uuid_returns_400(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.user_identities.list_from_user(room_uuid='not-a-uuid')

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
        result = self.chatd.user_identities.list_from_user(room_uuid=str(room.uuid))

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
        result = self.chatd.user_identities.list_from_user(room_uuid=str(room.uuid))

        assert result['total'] == 0
        assert result['items'] == []
