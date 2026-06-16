# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, Mock

import pytest

from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.types import AuthScope, ConfigField


class _FakeConnectorA:
    backend: ClassVar[str] = 'fake_a'
    supported_types: ClassVar[tuple[str, ...]] = ('sms',)


class _FakeConnectorB:
    backend: ClassVar[str] = 'fake_b'
    supported_types: ClassVar[tuple[str, ...]] = ('email', 'whatsapp')


def _make_connector_class(
    name: str = 'sample',
    auth_scope: AuthScope = 'tenant',
    auth_schema: tuple[ConfigField, ...] = (),
) -> type[Connector]:
    return type(
        f'_Sample_{name}',
        (),
        {
            'backend': name,
            'supported_types': ('sms',),
            'auth_scope': auth_scope,
            'auth_schema': auth_schema,
        },
    )


class TestConnectorRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()

    def test_available_backends_empty_on_init(self) -> None:
        assert self.registry.available_backends() == []

    def test_register_backend(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]

        assert self.registry.available_backends() == ['fake_a']

    def test_register_multiple_backends(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]
        self.registry.register_backend(_FakeConnectorB)  # type: ignore[arg-type]

        assert sorted(self.registry.available_backends()) == ['fake_a', 'fake_b']

    def test_get_backend(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]

        assert self.registry.get_backend('fake_a') is _FakeConnectorA

    def test_get_backend_unknown(self) -> None:
        with pytest.raises(KeyError):
            self.registry.get_backend('nonexistent')

    def test_register_backend_defaults_mode_to_webhook(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]

        assert self.registry.transport_mode('fake_a') == 'webhook'

    def test_register_backend_stores_mode(self) -> None:
        self.registry.register_backend(_FakeConnectorA, mode='poll')  # type: ignore[arg-type]

        assert self.registry.transport_mode('fake_a') == 'poll'

    def test_transport_mode_unknown_backend_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            self.registry.transport_mode('nonexistent')

    def test_register_backend_raises_on_duplicate(self) -> None:
        class _DuplicateConnector:
            backend: ClassVar[str] = 'fake_a'
            supported_types: ClassVar[tuple[str, ...]] = ('mms',)

        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            self.registry.register_backend(_DuplicateConnector)  # type: ignore[arg-type]

        assert self.registry.get_backend('fake_a') is _FakeConnectorA

    def test_resolve_reachable_types_caches_results(self) -> None:
        backend = Mock(
            backend='cached_fake',
            supported_types=('sms',),
            auth_scope='tenant',
            auth_schema=(),
            normalize_identity=Mock(return_value='+15551234'),
        )
        self.registry.register_backend(backend)

        self.registry.resolve_reachable_types('+15551234')
        self.registry.resolve_reachable_types('+15551234')
        self.registry.resolve_reachable_types('+15551234')

        backend.normalize_identity.assert_called_once_with('+15551234')

    def test_resolve_reachable_types_cache_invalidates_on_register(self) -> None:
        backend_a = Mock(
            backend='cached_a',
            supported_types=('sms',),
            auth_scope='tenant',
            auth_schema=(),
            normalize_identity=Mock(return_value='+15551234'),
        )
        self.registry.register_backend(backend_a)
        self.registry.resolve_reachable_types('+15551234')

        backend_b = Mock(
            backend='cached_b',
            supported_types=('mms',),
            auth_scope='tenant',
            auth_schema=(),
            normalize_identity=Mock(return_value='+15551234'),
        )
        self.registry.register_backend(backend_b)

        result = self.registry.resolve_reachable_types('+15551234')

        assert result == {'sms', 'mms'}

    def test_register_rejects_duplicate_field_names(self) -> None:
        cls = _make_connector_class(
            'dupe',
            auth_schema=(
                ConfigField(name='api_key', label={'en_US': 'A'}),
                ConfigField(name='api_key', label={'en_US': 'B'}),
            ),
        )

        with pytest.raises(ValueError, match='duplicate'):
            self.registry.register_backend(cls)  # type: ignore[arg-type]

    def test_register_rejects_none_scope_with_fields(self) -> None:
        cls = _make_connector_class(
            'bad_none',
            auth_scope='none',
            auth_schema=(ConfigField(name='api_key', label={'en_US': 'API Key'}),),
        )

        with pytest.raises(ValueError, match='none'):
            self.registry.register_backend(cls)  # type: ignore[arg-type]

        assert self.registry.available_backends() == []

    def test_register_rejects_invalid_auth_scope(self) -> None:
        cls = _make_connector_class('bad_scope', auth_scope='bogus')  # type: ignore[arg-type]

        with pytest.raises(ValueError, match='auth_scope'):
            self.registry.register_backend(cls)  # type: ignore[arg-type]

        assert self.registry.available_backends() == []

    def test_get_auth_schema_unknown_backend_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            self.registry.get_auth_schema('nonexistent')

    def test_get_auth_schema_returns_scope_and_serialized_fields(self) -> None:
        cls = _make_connector_class(
            'with_fields',
            auth_schema=(
                ConfigField(name='api_key', label={'en_US': 'API Key'}, type='secret'),
            ),
        )
        self.registry.register_backend(cls)  # type: ignore[arg-type]

        body, etag = self.registry.get_auth_schema('with_fields')

        assert json.loads(body) == {
            'scope': 'tenant',
            'fields': [
                {
                    'name': 'api_key',
                    'type': 'secret',
                    'required': True,
                    'default': '',
                    'label': [{'language': 'en_US', 'value': 'API Key'}],
                },
            ],
        }
        assert etag

    def test_get_auth_schema_etag_stable_across_calls(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]

        _, etag_a = self.registry.get_auth_schema('fake_a')
        _, etag_b = self.registry.get_auth_schema('fake_a')

        assert etag_a == etag_b

    def test_get_auth_schema_etag_differs_when_body_differs(self) -> None:
        none_cls = _make_connector_class('zero_cfg', auth_scope='none')
        tenant_cls = _make_connector_class('tenant_cfg', auth_scope='tenant')
        self.registry.register_backend(none_cls)  # type: ignore[arg-type]
        self.registry.register_backend(tenant_cls)  # type: ignore[arg-type]

        _, etag_none = self.registry.get_auth_schema('zero_cfg')
        _, etag_tenant = self.registry.get_auth_schema('tenant_cfg')

        assert etag_none != etag_tenant

    def test_get_auth_schema_returns_immutable_serialized_payload(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]

        body, _ = self.registry.get_auth_schema('fake_a')

        assert isinstance(body, str)
        assert json.loads(body) == {'scope': 'tenant', 'fields': []}

    def test_discover(self) -> None:
        mock_ext_a = Mock(spec=['name', 'plugin'])
        mock_ext_a.name = 'fake_a'
        mock_ext_a.plugin = _FakeConnectorA
        mock_ext_b = Mock(spec=['name', 'plugin'])
        mock_ext_b.name = 'fake_b'
        mock_ext_b.plugin = _FakeConnectorB

        mock_manager = MagicMock()
        mock_manager.__iter__.return_value = iter([mock_ext_a, mock_ext_b])

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.registry.ExtensionManager',
            return_value=mock_manager,
        ):
            self.registry.discover(
                connectors_config={
                    'fake_a': {'enabled': True},
                    'fake_b': {'enabled': True},
                }
            )

        assert sorted(self.registry.available_backends()) == ['fake_a', 'fake_b']

    def test_discover_skips_backend_with_invalid_mode(self) -> None:
        mock_ext_a = Mock(spec=['name', 'plugin'])
        mock_ext_a.name = 'fake_a'
        mock_ext_a.plugin = _FakeConnectorA
        mock_ext_b = Mock(spec=['name', 'plugin'])
        mock_ext_b.name = 'fake_b'
        mock_ext_b.plugin = _FakeConnectorB

        mock_manager = MagicMock()
        mock_manager.__iter__.return_value = iter([mock_ext_a, mock_ext_b])

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.registry.ExtensionManager',
            return_value=mock_manager,
        ):
            self.registry.discover(
                connectors_config={
                    'fake_a': {'enabled': True, 'mode': 'poll'},
                    'fake_b': {'enabled': True, 'mode': 'bogus'},
                }
            )

        assert self.registry.available_backends() == ['fake_a']

    def test_discover_stores_resolved_mode_per_backend(self) -> None:
        mock_ext_a = Mock(spec=['name', 'plugin'])
        mock_ext_a.name = 'fake_a'
        mock_ext_a.plugin = _FakeConnectorA
        mock_ext_b = Mock(spec=['name', 'plugin'])
        mock_ext_b.name = 'fake_b'
        mock_ext_b.plugin = _FakeConnectorB

        mock_manager = MagicMock()
        mock_manager.__iter__.return_value = iter([mock_ext_a, mock_ext_b])

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.registry.ExtensionManager',
            return_value=mock_manager,
        ):
            self.registry.discover(
                connectors_config={
                    'fake_a': {'enabled': True, 'mode': 'poll'},
                    'fake_b': {'enabled': True},
                }
            )

        assert self.registry.transport_mode('fake_a') == 'poll'
        assert self.registry.transport_mode('fake_b') == 'webhook'
