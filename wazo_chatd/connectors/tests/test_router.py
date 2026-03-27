# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import Mock

import pytest

from wazo_chatd.connectors.exceptions import ConnectorParseError
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.router import ConnectorRouter
from wazo_chatd.connectors.types import InboundMessage


class _SmsConnector:
    backend: ClassVar[str] = 'twilio'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    def normalize_identity(self, raw_identity: str) -> str:
        if raw_identity.startswith('+'):
            return raw_identity
        raise ValueError(f'Not a phone number: {raw_identity}')


class _EmailConnector:
    backend: ClassVar[str] = 'mailgun'
    supported_types: ClassVar[tuple[str, ...]] = ('email',)

    def normalize_identity(self, raw_identity: str) -> str:
        if '@' in raw_identity:
            return raw_identity.lower()
        raise ValueError(f'Not an email: {raw_identity}')


def _make_room_user(
    uuid: str = 'user-uuid',
    identity: str | None = None,
) -> Mock:
    user = Mock()
    user.uuid = uuid
    user.identity = identity
    return user


def _make_room(users: list[Mock] | None = None) -> Mock:
    room = Mock()
    room.users = users or []
    return room


def _build_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
    registry.register_backend(_EmailConnector)  # type: ignore[arg-type]
    return registry


class TestConnectorRouterListCapabilities(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.router = ConnectorRouter(registry=self.registry)

    def test_all_internal_users(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('user-b'),
            ]
        )

        capabilities = self.router.list_capabilities(room)

        assert capabilities == {'internal'}

    def test_external_phone_number(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )

        capabilities = self.router.list_capabilities(room)

        assert capabilities == {'sms', 'mms'}

    def test_external_email(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='bob@example.com'),
            ]
        )

        capabilities = self.router.list_capabilities(room)

        assert capabilities == {'email'}

    def test_external_unknown_identity(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='unknown-format'),
            ]
        )

        capabilities = self.router.list_capabilities(room)

        assert capabilities == set()

    def test_internal_excluded_when_external_present(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )

        capabilities = self.router.list_capabilities(room)

        assert 'internal' not in capabilities


class TestConnectorRouterDispatchWebhook(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        self.router = ConnectorRouter(registry=self.registry)
        self.on_message = Mock()
        self.router.on_message = self.on_message  # type: ignore[assignment]

    def test_dispatch_to_matching_connector(self) -> None:
        connector = Mock()
        connector.backend = 'twilio'
        inbound = InboundMessage(
            sender='+15559876',
            recipient='+15551234',
            body='hello',
            backend='twilio',
            external_id='msg-123',
        )
        connector.on_event.return_value = inbound
        self.router.add_instance('twilio-sms', connector)

        self.router.dispatch_webhook('twilio', {'From': '+15559876'})

        connector.on_event.assert_called_once_with('webhook', {'From': '+15559876'})
        self.on_message.assert_called_once_with(inbound)

    def test_dispatch_skips_none_events(self) -> None:
        connector = Mock()
        connector.backend = 'twilio'
        connector.on_event.return_value = None
        self.router.add_instance('twilio-sms', connector)

        self.router.dispatch_webhook('twilio', {'status': 'delivered'})

        connector.on_event.assert_called_once()
        self.on_message.assert_not_called()

    def test_dispatch_unknown_backend(self) -> None:
        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook('nonexistent', {})

    def test_dispatch_tries_all_instances_of_backend(self) -> None:
        connector_a = Mock()
        connector_a.backend = 'twilio'
        connector_a.on_event.return_value = None

        connector_b = Mock()
        connector_b.backend = 'twilio'
        inbound = InboundMessage(
            sender='+15559876',
            recipient='+15551234',
            body='hello',
            backend='twilio',
            external_id='msg-456',
        )
        connector_b.on_event.return_value = inbound

        self.router.add_instance('twilio-sms', connector_a)
        self.router.add_instance('twilio-mms', connector_b)

        self.router.dispatch_webhook('twilio', {'data': 'test'})

        self.on_message.assert_called_once_with(inbound)
