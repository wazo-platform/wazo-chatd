# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import Mock

from requests.exceptions import HTTPError

from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore

TENANT_A = 'tenant-a-uuid'
TENANT_B = 'tenant-b-uuid'


class _SmsConnector:
    backend: ClassVar[str] = 'twilio'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    def __init__(self, provider_config: object = None, connector_config: object = None) -> None:
        pass


class _EmailConnector:
    backend: ClassVar[str] = 'mailgun'
    supported_types: ClassVar[tuple[str, ...]] = ('email',)

    def __init__(self, provider_config: object = None, connector_config: object = None) -> None:
        pass


def _build_registry(*backends: type) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    for cls in backends:
        registry.register_backend(cls)  # type: ignore[arg-type]
    return registry


def _not_found() -> HTTPError:
    response = Mock(status_code=404)
    return HTTPError(response=response)


class TestConnectorStoreRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_config_from_auth(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        result = await store.refresh('twilio', TENANT_A)

        assert result is not None
        assert result.backend == 'twilio'
        auth_client.external.get_config.assert_called_once_with(
            'twilio', tenant_uuid=TENANT_A
        )

    async def test_skips_fresh_entry(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        await store.refresh('twilio', TENANT_A)
        await store.refresh('twilio', TENANT_A)

        auth_client.external.get_config.assert_called_once()

    async def test_different_tenants_get_separate_instances(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        a = await store.refresh('twilio', TENANT_A)
        b = await store.refresh('twilio', TENANT_B)

        assert a is not b
        assert auth_client.external.get_config.call_count == 2

    async def test_refetches_after_ttl_expires(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'v1'}
        store = ConnectorStore(
            auth_client, _build_registry(_SmsConnector), cache_ttl=0.0
        )

        await store.refresh('twilio', TENANT_A)
        await store.refresh('twilio', TENANT_A)

        assert auth_client.external.get_config.call_count == 2

    async def test_returns_none_for_unconfigured_backend(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = _not_found()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        result = await store.refresh('twilio', TENANT_A)

        assert result is None

    async def test_returns_none_for_unregistered_backend(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, _build_registry())

        result = await store.refresh('nonexistent', TENANT_A)

        assert result is None
        auth_client.external.get_config.assert_not_called()

    async def test_removes_stale_entry_on_404(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(
            auth_client, _build_registry(_SmsConnector), cache_ttl=0.0
        )

        await store.refresh('twilio', TENANT_A)
        assert store.find_by_backend('twilio', TENANT_A) is not None

        auth_client.external.get_config.side_effect = _not_found()
        await store.refresh('twilio', TENANT_A)
        assert store.find_by_backend('twilio', TENANT_A) is None


class TestConnectorStoreFindByBackend(unittest.TestCase):
    def test_returns_none_when_not_cached(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        result = store.find_by_backend('twilio', TENANT_A)

        assert result is None
        auth_client.external.get_config.assert_not_called()
