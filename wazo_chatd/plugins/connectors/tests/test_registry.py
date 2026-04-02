# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import MagicMock, Mock

import pytest

from wazo_chatd.plugins.connectors.registry import ConnectorRegistry


class _FakeConnectorA:
    backend: ClassVar[str] = 'fake_a'
    supported_types: ClassVar[tuple[str, ...]] = ('sms',)


class _FakeConnectorB:
    backend: ClassVar[str] = 'fake_b'
    supported_types: ClassVar[tuple[str, ...]] = ('email', 'whatsapp')


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

    def test_register_backend_overwrites_duplicate(self) -> None:
        class _DuplicateConnector:
            backend: ClassVar[str] = 'fake_a'
            supported_types: ClassVar[tuple[str, ...]] = ('mms',)

        self.registry.register_backend(_FakeConnectorA)  # type: ignore[arg-type]
        self.registry.register_backend(_DuplicateConnector)  # type: ignore[arg-type]

        assert self.registry.get_backend('fake_a') is _DuplicateConnector

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
