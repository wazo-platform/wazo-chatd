# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import requests

from .helpers import fixtures
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    TOKEN_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

RECIPIENT_UUID = uuid.uuid4()
PROVIDER_UUID = uuid.uuid4()
EXTERNAL_IDENTITY = 'test:+15559876'
SENDER_IDENTITY = 'test:+15551234'


def _get_aliases(port: int, room_uuid: str) -> requests.Response:
    # TODO: add list_room_aliases to wazo-chatd-client
    return requests.get(
        f'http://127.0.0.1:{port}/1.0/users/me/rooms/{room_uuid}/aliases',
        headers={
            'X-Auth-Token': str(TOKEN_UUID),
            'Wazo-Tenant': str(TOKEN_TENANT_UUID),
        },
    )


@use_asset('connectors')
class TestRoomAliases(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_UUID, 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_external_participant_returns_sender_aliases(
        self, sender, recipient, provider, alias, room
    ):
        self.reload_connectors()
        port = self.asset_cls.service_port(9304, 'chatd')

        response = _get_aliases(port, str(room.uuid))

        assert response.status_code == 200
        body = response.json()
        assert body['total'] >= 1
        identities = [item['identity'] for item in body['items']]
        assert SENDER_IDENTITY in identities

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=RECIPIENT_UUID)
    @fixtures.db.chat_provider(
        uuid=PROVIDER_UUID,
        name='Test Provider',
        type_='test',
        backend='test',
    )
    @fixtures.db.user_alias(
        user_uuid=TOKEN_USER_UUID,
        provider_uuid=PROVIDER_UUID,
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.user_alias(
        user_uuid=RECIPIENT_UUID,
        provider_uuid=PROVIDER_UUID,
        identity='test:+15557777',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': RECIPIENT_UUID},
        ],
    )
    def test_wazo_user_with_alias_returns_sender_aliases(
        self, sender, recipient, provider, sender_alias, recipient_alias, room
    ):
        self.reload_connectors()
        port = self.asset_cls.service_port(9304, 'chatd')

        response = _get_aliases(port, str(room.uuid))

        assert response.status_code == 200
        body = response.json()
        assert body['total'] >= 1
        identities = [item['identity'] for item in body['items']]
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
        port = self.asset_cls.service_port(9304, 'chatd')

        response = _get_aliases(port, str(room.uuid))

        assert response.status_code == 200
        body = response.json()
        assert body['total'] == 0
        assert body['items'] == []

    def test_unknown_room_returns_404(self):
        port = self.asset_cls.service_port(9304, 'chatd')
        unknown_uuid = str(uuid.uuid4())

        response = _get_aliases(port, unknown_uuid)

        assert response.status_code == 404
