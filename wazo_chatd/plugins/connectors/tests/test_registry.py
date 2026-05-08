# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import MagicMock, Mock

import pytest

from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

from ._factories import FakeConnector


class _FakeConnectorA(FakeConnector):
    backend: ClassVar[str] = 'fake_a'
    supported_types: ClassVar[tuple[str, ...]] = ('sms',)


class _FakeConnectorB(FakeConnector):
    backend: ClassVar[str] = 'fake_b'
    supported_types: ClassVar[tuple[str, ...]] = ('email', 'whatsapp')


class TestConnectorRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()

    def test_available_backends_empty_on_init(self) -> None:
        assert self.registry.available_backends() == []

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
            normalize_identity=Mock(return_value='+15551234'),
        )
        self.registry.register_backend(backend_a)
        self.registry.resolve_reachable_types('+15551234')

        backend_b = Mock(
            backend='cached_b',
            supported_types=('mms',),
            normalize_identity=Mock(return_value='+15551234'),
        )
        self.registry.register_backend(backend_b)

        result = self.registry.resolve_reachable_types('+15551234')

        assert result == {'sms', 'mms'}

    def test_types_for_backend_returns_supported_types(self) -> None:
        self.registry.register_backend(_FakeConnectorB)  # type: ignore[arg-type]

        assert self.registry.types_for_backend('fake_b') == {'email', 'whatsapp'}

    def test_types_for_backend_returns_empty_for_unknown(self) -> None:
        assert self.registry.types_for_backend('nonexistent') == set()

    def test_backends_for_types_returns_intersecting_backends(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]
        self.registry.register_backend(_FakeConnectorB)  # type: ignore[arg-type]

        assert self.registry.backends_for_types({'sms'}) == {'fake_a'}
        assert self.registry.backends_for_types({'email'}) == {'fake_b'}
        assert self.registry.backends_for_types({'sms', 'email'}) == {
            'fake_a',
            'fake_b',
        }

    def test_backends_for_types_returns_empty_when_no_intersection(self) -> None:
        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]

        assert self.registry.backends_for_types({'fax'}) == set()

    def test_discover_skips_disabled_entries(self) -> None:
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
                    'fake_b': {'enabled': False},
                }
            )

        assert self.registry.available_backends() == ['fake_a']

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
