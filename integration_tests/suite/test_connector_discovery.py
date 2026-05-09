# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest
from wazo_chatd_client.exceptions import ChatdError

from .helpers.base import (
    ConnectorIntegrationTest,
    use_asset,
)


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
        # setUpClass sets external_config for 'test' backend.
        result = self.chatd.connectors.list()

        test_connector = next(c for c in result['items'] if c['name'] == 'test')
        assert test_connector['configured'] is True

    def test_list_response_includes_webhook_url(self):
        result = self.chatd.connectors.list()

        test_connector = next(c for c in result['items'] if c['name'] == 'test')
        assert test_connector['webhook_url'].endswith('/connectors/incoming/test')


@use_asset('connectors')
class TestConnectorListAuth(ConnectorIntegrationTest):
    def test_missing_or_invalid_token_returns_401(self):
        for bad_token in ['', str(uuid.uuid4())]:
            chatd = self.asset_cls.make_chatd(token=bad_token)

            with pytest.raises(ChatdError) as exc_info:
                chatd.connectors.list()

            assert exc_info.value.status_code == 401
