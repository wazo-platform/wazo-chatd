# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import ConnectorIntegrationTest, use_asset


@use_asset('connectors')
class TestConnectorList(ConnectorIntegrationTest):
    def test_list_returns_registered_connectors(self):
        result = self.chatd.connectors.list()

        assert result['total'] >= 1
        names = [c['name'] for c in result['items']]
        assert 'test' in names

    def test_list_response_includes_supported_types(self):
        result = self.chatd.connectors.list()

        test_connector = next(c for c in result['items'] if c['name'] == 'test')
        assert sorted(test_connector['supported_types']) == ['test', 'test_alt']

    def test_list_marks_configured_when_external_config_set(self):
        result = self.chatd.connectors.list()

        test_connector = next(c for c in result['items'] if c['name'] == 'test')
        assert test_connector['configured'] is True

    def test_list_response_includes_webhook_url(self):
        result = self.chatd.connectors.list()

        test_connector = next(c for c in result['items'] if c['name'] == 'test')
        assert test_connector['webhook_url'].endswith('/connectors/incoming/test')


@use_asset('connectors')
class TestConnectorInventory(ConnectorIntegrationTest):
    def test_inventory_returns_provider_identities(self):
        result = self.chatd.connectors.inventory('test')

        assert result['total'] >= 2
        identities = {item['identity'] for item in result['items']}
        assert 'test:provider-1' in identities
        assert 'test:provider-2' in identities

    def test_inventory_marks_unbound_identities(self):
        result = self.chatd.connectors.inventory('test')

        item = next(i for i in result['items'] if i['identity'] == 'test:provider-1')
        assert item['binding'] is None

    @fixtures.db.user_identity(
        backend='test',
        type_='test',
        identity='test:provider-1',
    )
    def test_inventory_marks_bound_identities(self, identity):
        result = self.chatd.connectors.inventory('test')

        item = next(i for i in result['items'] if i['identity'] == 'test:provider-1')
        assert item['binding'] is not None
        assert item['binding']['uuid'] == str(identity.uuid)
        assert item['binding']['user_uuid'] == str(identity.user_uuid)

    def test_inventory_unknown_backend_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.connectors.inventory('nonexistent-backend')

        assert exc_info.value.status_code == 404
        assert exc_info.value.error_id == 'no-such-connector'


@use_asset('connectors')
class TestConnectorListAuth(ConnectorIntegrationTest):
    def test_missing_or_invalid_token_returns_401(self):
        for bad_token in ['', str(uuid.uuid4())]:
            chatd = self.asset_cls.make_chatd(token=bad_token)

            with pytest.raises(ChatdError) as exc_info:
                chatd.connectors.list()

            assert exc_info.value.status_code == 401

    def test_inventory_missing_or_invalid_token_returns_401(self):
        for bad_token in ['', str(uuid.uuid4())]:
            chatd = self.asset_cls.make_chatd(token=bad_token)

            with pytest.raises(ChatdError) as exc_info:
                chatd.connectors.inventory('test')

            assert exc_info.value.status_code == 401
