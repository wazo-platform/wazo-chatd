# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import requests

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


def _identity_url(port: int, user_uuid: str, identity_uuid: str | None = None) -> str:
    base = f'http://127.0.0.1:{port}/1.0/users/{user_uuid}/identities'
    if identity_uuid:
        return f'{base}/{identity_uuid}'
    return base


def _headers(tenant_uuid: str = str(TOKEN_TENANT_UUID)) -> dict[str, str]:
    return {
        'X-Auth-Token': str(TOKEN_UUID),
        'Wazo-Tenant': tenant_uuid,
        'Content-Type': 'application/json',
    }


@use_asset('connectors')
class TestUserIdentityCRUD(ConnectorIntegrationTest):
    @property
    def port(self) -> int:
        return self.asset_cls.service_port(9304, 'chatd')

    @fixtures.db.user(uuid=USER_UUID)
    def test_list_empty(self, user):
        response = requests.get(
            _identity_url(self.port, str(USER_UUID)),
            headers=_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body['items'] == []
        assert body['total'] == 0

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_list_returns_identities(self, user, identity):
        response = requests.get(
            _identity_url(self.port, str(USER_UUID)),
            headers=_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body['total'] == 1
        assert body['items'][0]['backend'] == 'twilio'
        assert body['items'][0]['type'] == 'sms'
        assert body['items'][0]['identity'] == '+15551234567'

    @fixtures.db.user(uuid=USER_UUID)
    def test_create(self, user):
        response = requests.post(
            _identity_url(self.port, str(USER_UUID)),
            headers=_headers(),
            json={
                'backend': 'twilio',
                'type': 'sms',
                'identity': '+15559999999',
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body['backend'] == 'twilio'
        assert body['type'] == 'sms'
        assert body['identity'] == '+15559999999'
        assert 'uuid' in body

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_with_extra(self, user):
        response = requests.post(
            _identity_url(self.port, str(USER_UUID)),
            headers=_headers(),
            json={
                'backend': 'twilio',
                'type': 'sms',
                'identity': '+15558888888',
                'extra': {'account_sid': 'AC123'},
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body['type'] == 'sms'
        assert body['extra'] == {'account_sid': 'AC123'}

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_missing_backend_returns_400(self, user):
        response = requests.post(
            _identity_url(self.port, str(USER_UUID)),
            headers=_headers(),
            json={'type': 'sms', 'identity': '+15557777777'},
        )

        assert response.status_code == 400

    @fixtures.db.user(uuid=USER_UUID)
    def test_create_missing_identity_returns_400(self, user):
        response = requests.post(
            _identity_url(self.port, str(USER_UUID)),
            headers=_headers(),
            json={'backend': 'twilio', 'type': 'sms'},
        )

        assert response.status_code == 400

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_get(self, user, identity):
        response = requests.get(
            _identity_url(self.port, str(USER_UUID), str(identity.uuid)),
            headers=_headers(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body['uuid'] == str(identity.uuid)
        assert body['backend'] == 'twilio'
        assert body['type'] == 'sms'
        assert body['identity'] == '+15551234567'

    @fixtures.db.user(uuid=USER_UUID)
    def test_get_unknown_returns_404(self, user):
        unknown = str(uuid.uuid4())
        response = requests.get(
            _identity_url(self.port, str(USER_UUID), unknown),
            headers=_headers(),
        )

        assert response.status_code == 404

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_update(self, user, identity):
        response = requests.put(
            _identity_url(self.port, str(USER_UUID), str(identity.uuid)),
            headers=_headers(),
            json={
                'backend': 'vonage',
                'type': 'sms',
                'identity': '+15550000000',
            },
        )

        assert response.status_code == 204

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_delete(self, user, identity):
        identity_uuid = str(identity.uuid)

        response = requests.delete(
            _identity_url(self.port, str(USER_UUID), identity_uuid),
            headers=_headers(),
        )

        assert response.status_code == 204

        response = requests.get(
            _identity_url(self.port, str(USER_UUID), identity_uuid),
            headers=_headers(),
        )

        assert response.status_code == 404

    @fixtures.db.user(uuid=USER_UUID)
    def test_delete_unknown_returns_404(self, user):
        unknown = str(uuid.uuid4())
        response = requests.delete(
            _identity_url(self.port, str(USER_UUID), unknown),
            headers=_headers(),
        )

        assert response.status_code == 404


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

        response = requests.get(
            _identity_url(self.port, str(OTHER_TENANT_USER_UUID)),
            headers={
                'X-Auth-Token': token,
                'Wazo-Tenant': str(OTHER_TENANT_UUID),
                'Content-Type': 'application/json',
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body['total'] == 1
        assert body['items'][0]['identity'] == '+15553334444'

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

        response = requests.get(
            _identity_url(self.port, str(USER_UUID)),
            headers={
                'X-Auth-Token': other_token,
                'Wazo-Tenant': str(TOKEN_TENANT_UUID),
                'Content-Type': 'application/json',
            },
        )

        assert response.status_code == 401
