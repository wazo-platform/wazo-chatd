# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
import requests
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import TOKEN_SUBTENANT_UUID as OTHER_TENANT_UUID
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

USER_UUID = uuid.uuid4()
OTHER_TENANT_USER_UUID = uuid.uuid4()


def _identity_url(port: int, user_uuid: str) -> str:
    return f'http://127.0.0.1:{port}/1.0/users/{user_uuid}/identities'


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
            {'backend': 'twilio', 'type': 'sms', 'identity': '+15559999999'},
        )

        assert result['backend'] == 'twilio'
        assert result['type'] == 'sms'
        assert result['identity'] == '+15559999999'
        assert 'uuid' in result

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_with_extra(self, user):
        result = self.chatd.user_identities.create(
            str(USER_UUID),
            {
                'backend': 'twilio',
                'type': 'sms',
                'identity': '+15558888888',
                'extra': {'account_sid': 'AC123'},
            },
        )

        assert result['type'] == 'sms'
        assert result['extra'] == {'account_sid': 'AC123'}

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
        result = self.chatd.user_identities.get(
            str(USER_UUID), str(identity.uuid)
        )

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
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_update(self, user, identity):
        self.chatd.user_identities.update(
            str(USER_UUID),
            str(identity.uuid),
            {'backend': 'vonage', 'type': 'sms', 'identity': '+15550000000'},
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
    @property
    def port(self) -> int:
        return self.asset_cls.service_port(9304, 'chatd')

    def test_no_token_returns_401(self):
        response = requests.get(
            _identity_url(self.port, str(USER_UUID)),
            headers={'Content-Type': 'application/json'},
        )

        assert response.status_code == 401

    def test_invalid_token_returns_401(self):
        response = requests.get(
            _identity_url(self.port, str(USER_UUID)),
            headers={
                'X-Auth-Token': str(uuid.uuid4()),
                'Content-Type': 'application/json',
            },
        )

        assert response.status_code == 401

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
