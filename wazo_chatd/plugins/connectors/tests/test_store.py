# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import Mock

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError

from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    BackendNotConfiguredException,
    UnknownBackendException,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore

TENANT_A = 'tenant-a-uuid'
TENANT_B = 'tenant-b-uuid'


class _SmsConnector:
    backend: ClassVar[str] = 'sms_backend'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    def __init__(
        self,
        tenant_uuid: str,
        provider_config: dict | None = None,
        connector_config: dict | None = None,
    ) -> None:
        self.tenant_uuid = tenant_uuid
        self.provider_config = provider_config
        self.connector_config = connector_config


class _EmailConnector:
    backend: ClassVar[str] = 'email_backend'
    supported_types: ClassVar[tuple[str, ...]] = ('email',)

    def __init__(
        self,
        tenant_uuid: str,
        provider_config: dict | None = None,
        connector_config: dict | None = None,
    ) -> None:
        self.tenant_uuid = tenant_uuid


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

        result = await store.refresh('sms_backend', TENANT_A)

        assert result is not None
        assert result.backend == 'sms_backend'
        auth_client.external.get_config.assert_called_once_with(
            'sms_backend', tenant_uuid=TENANT_A
        )

    async def test_skips_fresh_entry(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        await store.refresh('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_A)

        auth_client.external.get_config.assert_called_once()

    async def test_different_tenants_get_separate_instances(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        a = await store.refresh('sms_backend', TENANT_A)
        b = await store.refresh('sms_backend', TENANT_B)

        assert a is not b
        assert auth_client.external.get_config.call_count == 2

    async def test_instance_is_constructed_with_tenant_uuid(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        instance = await store.refresh('sms_backend', TENANT_A)

        assert instance is not None
        assert instance.tenant_uuid == TENANT_A  # type: ignore[attr-defined]

    async def test_refetches_after_ttl_expires(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'v1'}
        store = ConnectorStore(
            auth_client, _build_registry(_SmsConnector), cache_ttl=0.0
        )

        await store.refresh('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_A)

        assert auth_client.external.get_config.call_count == 2

    async def test_returns_none_for_unconfigured_backend(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = _not_found()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        result = await store.refresh('sms_backend', TENANT_A)

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

        await store.refresh('sms_backend', TENANT_A)
        assert store.find_by_backend('sms_backend', TENANT_A) is not None

        auth_client.external.get_config.side_effect = _not_found()
        await store.refresh('sms_backend', TENANT_A)
        assert store.find_by_backend('sms_backend', TENANT_A) is None


class TestConnectorStoreFindByBackend(unittest.TestCase):
    def test_returns_none_when_not_cached(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        result = store.find_by_backend('sms_backend', TENANT_A)

        assert result is None
        auth_client.external.get_config.assert_not_called()


class TestConnectorStoreDrop(unittest.IsolatedAsyncioTestCase):
    async def test_removes_cached_entry(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))
        await store.refresh('sms_backend', TENANT_A)
        assert store.find_by_backend('sms_backend', TENANT_A) is not None

        store.drop('sms_backend', TENANT_A)

        assert store.find_by_backend('sms_backend', TENANT_A) is None

    async def test_is_idempotent_when_entry_missing(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        store.drop('sms_backend', TENANT_A)

        assert store.find_by_backend('sms_backend', TENANT_A) is None

    async def test_only_drops_target_tenant(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))
        await store.refresh('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_B)

        store.drop('sms_backend', TENANT_A)

        assert store.find_by_backend('sms_backend', TENANT_A) is None
        assert store.find_by_backend('sms_backend', TENANT_B) is not None

    async def test_refetches_after_drop(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))
        await store.refresh('sms_backend', TENANT_A)

        store.drop('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_A)

        assert auth_client.external.get_config.call_count == 2
        assert store.find_by_backend('sms_backend', TENANT_A) is not None


class TestConnectorStoreFetch(unittest.TestCase):
    def test_success_returns_instance_and_populates_cache(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        instance = store.fetch('sms_backend', TENANT_A)

        assert instance.backend == 'sms_backend'
        assert store.find_by_backend('sms_backend', TENANT_A) is instance

    def test_returns_cached_instance_when_fresh(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        first = store.fetch('sms_backend', TENANT_A)
        second = store.fetch('sms_backend', TENANT_A)

        assert first is second
        auth_client.external.get_config.assert_called_once()

    def test_raises_backend_not_configured_on_404(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = _not_found()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        with self.assertRaises(BackendNotConfiguredException):
            store.fetch('sms_backend', TENANT_A)

    def test_raises_auth_unavailable_on_5xx(self) -> None:
        auth_client = Mock()
        response = Mock(status_code=503)
        auth_client.external.get_config.side_effect = HTTPError(response=response)
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        with self.assertRaises(AuthServiceUnavailableException):
            store.fetch('sms_backend', TENANT_A)

    def test_raises_auth_unavailable_on_connection_error(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = RequestsConnectionError()
        store = ConnectorStore(auth_client, _build_registry(_SmsConnector))

        with self.assertRaises(AuthServiceUnavailableException):
            store.fetch('sms_backend', TENANT_A)

    def test_raises_unknown_backend_for_unregistered_backend(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, _build_registry())

        with self.assertRaises(UnknownBackendException):
            store.fetch('sms_backend', TENANT_A)

        auth_client.external.get_config.assert_not_called()


class TestConnectorStorePopulate(unittest.IsolatedAsyncioTestCase):
    async def test_wait_populated_resolves_on_success(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(
            auth_client,
            _build_registry(_SmsConnector),
            connectors_config={'sms_backend': {'mode': 'poll'}},
        )

        store.populate([(TENANT_A, 'sms_backend')])

        await store.wait_populated()

    async def test_wait_populated_raises_on_priority_fetch_failure(self) -> None:
        auth_client = Mock()
        registry = Mock()
        registry.available_backends.side_effect = RuntimeError('registry boom')
        store = ConnectorStore(auth_client, registry)

        with self.assertRaises(RuntimeError):
            store.populate([(TENANT_A, 'sms_backend')])

        with self.assertRaises(RuntimeError):
            await store.wait_populated()
