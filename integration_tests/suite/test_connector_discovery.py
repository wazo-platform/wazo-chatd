# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError
from wazo_test_helpers import until

from .helpers import fixtures
from .helpers.base import TOKEN_TENANT_UUID, ConnectorIntegrationTest, use_asset


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


@use_asset('connectors')
class TestConnectorIdentities(ConnectorIntegrationTest):
    def test_identities_returns_backend_identities(self):
        result = self.chatd.connectors.identities('test')

        assert result['total'] >= 2
        identities = {item['identity'] for item in result['items']}
        assert 'test:backend-1' in identities
        assert 'test:backend-2' in identities

    def test_identities_marks_unbound_identities(self):
        result = self.chatd.connectors.identities('test')

        item = next(i for i in result['items'] if i['identity'] == 'test:backend-1')
        assert item['binding'] is None

    @fixtures.db.user_identity(
        backend='test',
        type_='test',
        identity='test:backend-1',
    )
    def test_identities_marks_bound_identities(self, identity):
        result = self.chatd.connectors.identities('test')

        item = next(i for i in result['items'] if i['identity'] == 'test:backend-1')
        assert item['binding'] is not None
        assert item['binding']['identity_uuid'] == str(identity.uuid)
        assert item['binding']['user_uuid'] == str(identity.user_uuid)

    def test_identities_unknown_backend_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.connectors.identities('nonexistent-backend')

        assert exc_info.value.status_code == 404
        assert exc_info.value.error_id == 'no-such-connector'


@use_asset('connectors')
class TestConnectorAuthSchema(ConnectorIntegrationTest):
    def test_returns_declared_fields(self):
        body = self.chatd.connectors.auth_schema('test')

        assert body['scope'] == 'tenant'
        names = [f['name'] for f in body['fields']]
        assert names == ['api_key', 'region']

        api_key = body['fields'][0]
        assert api_key['type'] == 'secret'
        assert api_key['label'] == [
            {'language': 'en_US', 'value': 'API Key'},
            {'language': 'fr_FR', 'value': 'Clé API'},
        ]
        assert 'choices' not in api_key

        region = body['fields'][1]
        assert region['type'] == 'select'
        assert region['choices'] == ['us', 'eu']
        assert region['default'] == 'us'

    def test_unknown_backend_returns_404(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.connectors.auth_schema('nonexistent-backend')

        assert exc_info.value.status_code == 404
        assert exc_info.value.error_id == 'no-such-connector'

    def test_missing_or_invalid_token_returns_401(self):
        for bad_token in ['', str(uuid.uuid4())]:
            chatd = self.asset_cls.make_chatd(token=bad_token)

            with pytest.raises(ChatdError) as exc_info:
                chatd.connectors.auth_schema('test')

            assert exc_info.value.status_code == 401


@use_asset('connectors')
class TestConnectorListAuth(ConnectorIntegrationTest):
    def test_missing_or_invalid_token_returns_401(self):
        for bad_token in ['', str(uuid.uuid4())]:
            chatd = self.asset_cls.make_chatd(token=bad_token)

            with pytest.raises(ChatdError) as exc_info:
                chatd.connectors.list()

            assert exc_info.value.status_code == 401

    def test_identities_missing_or_invalid_token_returns_401(self):
        for bad_token in ['', str(uuid.uuid4())]:
            chatd = self.asset_cls.make_chatd(token=bad_token)

            with pytest.raises(ChatdError) as exc_info:
                chatd.connectors.identities('test')

            assert exc_info.value.status_code == 401


@use_asset('connectors')
class TestConnectorIdentitiesBackendNotConfigured(ConnectorIntegrationTest):
    def setUp(self):
        super().setUp()
        self.addCleanup(
            self.auth.set_external_config,
            {'test': {'mock_url': 'http://connector-mock:8080'}},
        )
        self.auth.set_external_config({})
        self.bus.send_tenant_external_auth_deleted_event(TOKEN_TENANT_UUID, 'test')

        def cache_invalidated():
            result = self.chatd.connectors.list()
            test_connector = next(c for c in result['items'] if c['name'] == 'test')
            assert test_connector['configured'] is False

        until.assert_(cache_invalidated, timeout=5, interval=0.1)

    def test_identities_returns_400_when_backend_not_configured(self):
        with pytest.raises(ChatdError) as exc_info:
            self.chatd.connectors.identities('test')

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_id == 'backend-not-configured'
