# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError

from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    BackendNotConfiguredException,
    UnknownBackendException,
)
from wazo_chatd.plugins.connectors.store import ConnectorStore

from ._factories import FakeConnector, build_registry

TENANT_A = 'tenant-a-uuid'
TENANT_B = 'tenant-b-uuid'


class _SmsConnector(FakeConnector):
    backend: ClassVar[str] = 'sms_backend'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')


def _not_found() -> HTTPError:
    response = Mock(status_code=404)
    return HTTPError(response=response)


class TestConnectorStoreRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_config_from_auth(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        result = await store.refresh('sms_backend', TENANT_A)

        assert result is not None
        assert result.backend == 'sms_backend'
        auth_client.external.get_config.assert_called_once_with(
            'sms_backend', tenant_uuid=TENANT_A
        )

    async def test_skips_fresh_entry(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        await store.refresh('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_A)

        auth_client.external.get_config.assert_called_once()

    async def test_different_tenants_get_separate_instances(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        a = await store.refresh('sms_backend', TENANT_A)
        b = await store.refresh('sms_backend', TENANT_B)

        assert a is not b
        assert auth_client.external.get_config.call_count == 2

    async def test_instance_is_constructed_with_tenant_uuid(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        instance = await store.refresh('sms_backend', TENANT_A)

        assert instance is not None
        assert instance.tenant_uuid == TENANT_A  # type: ignore[attr-defined]

    async def test_refetches_after_ttl_expires(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'v1'}
        store = ConnectorStore(
            auth_client, build_registry(_SmsConnector), cache_ttl=0.0
        )

        await store.refresh('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_A)

        assert auth_client.external.get_config.call_count == 2

    async def test_returns_none_for_unconfigured_backend(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = _not_found()
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        result = await store.refresh('sms_backend', TENANT_A)

        assert result is None

    async def test_returns_none_for_unregistered_backend(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, build_registry())

        result = await store.refresh('nonexistent', TENANT_A)

        assert result is None
        auth_client.external.get_config.assert_not_called()

    async def test_removes_stale_entry_on_404(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(
            auth_client, build_registry(_SmsConnector), cache_ttl=0.0
        )

        await store.refresh('sms_backend', TENANT_A)
        assert store.peek('sms_backend', TENANT_A) is not None

        auth_client.external.get_config.side_effect = _not_found()
        await store.refresh('sms_backend', TENANT_A)
        assert store.peek('sms_backend', TENANT_A) is None


class TestConnectorStoreCacheEpochLifecycle(unittest.TestCase):
    def test_drop_without_pending_fetch_leaves_epoch_empty(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        store.drop('sms_backend', TENANT_A)
        store.drop('sms_backend', TENANT_A)
        store.drop('sms_backend', TENANT_B)

        assert store._cache_epoch == {}

    def test_repeated_drop_find_cycles_do_not_grow_epoch(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        for _ in range(10):
            store.find('sms_backend', TENANT_A)
            store.drop('sms_backend', TENANT_A)

        assert store._cache_epoch == {}

    def test_drop_during_fetch_records_epoch_and_cleans_up(self) -> None:
        auth_client = Mock()
        fetch_can_proceed = threading.Event()
        fetch_started = threading.Event()

        def slow_get_config(backend: str, tenant_uuid: str) -> dict[str, str]:
            fetch_started.set()
            fetch_can_proceed.wait(timeout=2)
            return {'token': 'old'}

        auth_client.external.get_config = slow_get_config
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(store.find, 'sms_backend', TENANT_A)

            assert fetch_started.wait(timeout=1)
            store.drop('sms_backend', TENANT_A)

            fetch_can_proceed.set()
            future.result(timeout=2)

        assert store.peek('sms_backend', TENANT_A) is None
        assert store._cache_epoch == {}


class TestConnectorStorePeek(unittest.TestCase):
    def test_returns_none_when_not_cached(self) -> None:
        auth_client = Mock()
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        result = store.peek('sms_backend', TENANT_A)

        assert result is None
        auth_client.external.get_config.assert_not_called()


class TestConnectorStoreDrop(unittest.IsolatedAsyncioTestCase):
    async def test_removes_cached_entry(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))
        await store.refresh('sms_backend', TENANT_A)
        assert store.peek('sms_backend', TENANT_A) is not None

        store.drop('sms_backend', TENANT_A)

        assert store.peek('sms_backend', TENANT_A) is None

    async def test_only_drops_target_tenant(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))
        await store.refresh('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_B)

        store.drop('sms_backend', TENANT_A)

        assert store.peek('sms_backend', TENANT_A) is None
        assert store.peek('sms_backend', TENANT_B) is not None

    async def test_refetches_after_drop(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))
        await store.refresh('sms_backend', TENANT_A)

        store.drop('sms_backend', TENANT_A)
        await store.refresh('sms_backend', TENANT_A)

        assert auth_client.external.get_config.call_count == 2
        assert store.peek('sms_backend', TENANT_A) is not None


class TestConnectorStoreGet(unittest.TestCase):
    def test_success_returns_instance_and_populates_cache(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        instance = store.get('sms_backend', TENANT_A)

        assert instance.backend == 'sms_backend'
        assert store.peek('sms_backend', TENANT_A) is instance

    def test_returns_cached_instance_when_fresh(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        first = store.get('sms_backend', TENANT_A)
        second = store.get('sms_backend', TENANT_A)

        assert first is second
        auth_client.external.get_config.assert_called_once()

    def test_raises_backend_not_configured_on_404(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = _not_found()
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with self.assertRaises(BackendNotConfiguredException):
            store.get('sms_backend', TENANT_A)

    def test_raises_auth_unavailable_on_5xx(self) -> None:
        auth_client = Mock()
        response = Mock(status_code=503)
        auth_client.external.get_config.side_effect = HTTPError(response=response)
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with self.assertRaises(AuthServiceUnavailableException):
            store.get('sms_backend', TENANT_A)

    def test_raises_auth_unavailable_on_connection_error(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = RequestsConnectionError()
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with self.assertRaises(AuthServiceUnavailableException):
            store.get('sms_backend', TENANT_A)

    def test_raises_auth_unavailable_when_http_error_has_no_response(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = HTTPError()
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with self.assertRaises(AuthServiceUnavailableException):
            store.get('sms_backend', TENANT_A)

    def test_raises_unknown_backend_for_unregistered_backend(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(auth_client, build_registry())

        with self.assertRaises(UnknownBackendException):
            store.get('sms_backend', TENANT_A)

        auth_client.external.get_config.assert_not_called()

    def test_concurrent_get_dedups_to_single_auth_call(self) -> None:
        both_arrived = threading.Barrier(2)
        release = threading.Event()

        def slow_get_config(*_args: object, **_kwargs: object) -> dict:
            both_arrived.wait(timeout=2)
            release.wait(timeout=2)
            return {'api_key': 'secret'}

        auth_client = Mock()
        auth_client.external.get_config.side_effect = slow_get_config
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(store.get, 'sms_backend', TENANT_A)
            f2 = pool.submit(store.get, 'sms_backend', TENANT_A)
            both_arrived.wait(timeout=2)
            release.set()
            r1 = f1.result(timeout=2)
            r2 = f2.result(timeout=2)

        assert r1 is r2
        assert auth_client.external.get_config.call_count == 1

    def test_concurrent_get_propagates_exception_to_followers(self) -> None:
        both_arrived = threading.Barrier(2)
        release = threading.Event()

        def slow_get_config(*_args: object, **_kwargs: object) -> dict:
            both_arrived.wait(timeout=2)
            release.wait(timeout=2)
            raise RequestsConnectionError()

        auth_client = Mock()
        auth_client.external.get_config.side_effect = slow_get_config
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(store.get, 'sms_backend', TENANT_A)
            f2 = pool.submit(store.get, 'sms_backend', TENANT_A)
            both_arrived.wait(timeout=2)
            release.set()

            with self.assertRaises(AuthServiceUnavailableException):
                f1.result(timeout=2)
            with self.assertRaises(AuthServiceUnavailableException):
                f2.result(timeout=2)

        assert auth_client.external.get_config.call_count == 1

    def test_expiry_is_jittered_to_avoid_stampede(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}

        with patch(
            'wazo_chatd.plugins.connectors.store.time.monotonic', return_value=1000.0
        ):
            store = ConnectorStore(
                auth_client, build_registry(_SmsConnector), cache_ttl=100.0
            )
            for i in range(50):
                store.get('sms_backend', f'tenant-{i}')

        initial = auth_client.external.get_config.call_count
        assert initial == 50

        with patch(
            'wazo_chatd.plugins.connectors.store.time.monotonic',
            return_value=1000.0 + 100.5,
        ):
            for i in range(50):
                store.get('sms_backend', f'tenant-{i}')

        refreshed = auth_client.external.get_config.call_count - initial
        assert 5 < refreshed < 45

    def test_sequential_gets_after_failure_can_retry(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.side_effect = [
            RequestsConnectionError(),
            {'api_key': 'secret'},
        ]
        store = ConnectorStore(auth_client, build_registry(_SmsConnector))

        with self.assertRaises(AuthServiceUnavailableException):
            store.get('sms_backend', TENANT_A)

        instance = store.get('sms_backend', TENANT_A)

        assert instance.backend == 'sms_backend'
        assert auth_client.external.get_config.call_count == 2


class TestConnectorStorePopulate(unittest.IsolatedAsyncioTestCase):
    async def test_wait_populated_resolves_on_success(self) -> None:
        auth_client = Mock()
        auth_client.external.get_config.return_value = {'api_key': 'secret'}
        store = ConnectorStore(
            auth_client,
            build_registry(_SmsConnector),
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
