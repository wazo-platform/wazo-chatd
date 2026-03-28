# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import Mock

import pytest

from wazo_chatd.connectors.exceptions import ConnectorParseError, NoCommonConnectorError
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
        self.router = ConnectorRouter(registry=self.registry, dao=Mock())

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
        self.router = ConnectorRouter(registry=self.registry, dao=Mock())
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


class TestConnectorRouterSend(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.dao = Mock()
        self.dao.user_alias.list_by_user_and_types.return_value = []
        self.manager = Mock()
        self.router = ConnectorRouter(registry=self.registry, dao=self.dao)
        self.router.set_manager(self.manager)

    def test_send_internal_room_is_noop(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('user-b'),
            ]
        )
        message = Mock(uuid='msg-uuid', user_uuid='user-a', content='hi')

        self.router.send(room, message)

        self.dao.room.add_message_meta.assert_not_called()
        self.manager.send_message.assert_not_called()

    def test_send_external_room_creates_meta_and_enqueues(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        message = Mock(uuid='msg-uuid', user_uuid='user-a', content='hello')

        alias = Mock()
        alias.identity = '+15551234'
        alias.provider = Mock(type_='sms', backend='twilio')
        self.dao.user_alias.list_by_user_and_types.return_value = [alias]

        self.router.send(room, message)

        self.dao.room.add_message_meta.assert_called_once()
        self.manager.send_message.assert_called_once()
        outbound = self.manager.send_message.call_args[0][0]
        assert outbound.sender_alias == '+15551234'
        assert outbound.recipient_alias == '+15559876'
        assert outbound.body == 'hello'

    def test_send_no_capabilities_raises(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='unknown-format'),
            ]
        )
        message = Mock(uuid='msg-uuid')

        with pytest.raises(NoCommonConnectorError):
            self.router.send(room, message)


class TestConnectorRouterOnMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.dao = Mock()
        self.notifier = Mock()
        self.router = ConnectorRouter(registry=self.registry, dao=self.dao)
        self.router.set_notifier(self.notifier)

    def _make_inbound(
        self,
        sender: str = '+15559876',
        recipient: str = '+15551234',
        body: str = 'hello',
        backend: str = 'twilio',
        external_id: str = 'ext-123',
        metadata: dict[str, str] | None = None,
    ) -> InboundMessage:
        return InboundMessage(
            sender=sender,
            recipient=recipient,
            body=body,
            backend=backend,
            external_id=external_id,
            metadata=metadata or {},
        )

    def test_on_message_persists_room_message_and_meta(self) -> None:
        inbound = self._make_inbound()

        # Mock room resolution
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        self.router.set_room_resolver(
            lambda tenant, sender, recipient: room,
        )

        self.router.on_message(inbound)

        # Should persist RoomMessage + MessageMeta
        self.dao.room.add_message.assert_called_once()

    def test_on_message_notifies(self) -> None:
        inbound = self._make_inbound()

        room = _make_room([_make_room_user('user-a')])
        self.router.set_room_resolver(
            lambda tenant, sender, recipient: room,
        )

        self.router.on_message(inbound)

        self.notifier.message_created.assert_called_once()

    def test_on_message_dedup_skips_duplicate(self) -> None:
        inbound = self._make_inbound(
            metadata={'idempotency_key': 'idem-abc'},
        )

        # Simulate existing message with this key
        self.router.set_dedup_checker(
            lambda key: True,  # key already exists
        )

        room = _make_room([_make_room_user('user-a')])
        self.router.set_room_resolver(
            lambda tenant, sender, recipient: room,
        )

        self.router.on_message(inbound)

        # Should NOT persist anything — duplicate
        self.dao.room.add_message.assert_not_called()
        self.notifier.message_created.assert_not_called()

    def test_on_message_dedup_allows_new_key(self) -> None:
        inbound = self._make_inbound(
            metadata={'idempotency_key': 'new-key'},
        )

        self.router.set_dedup_checker(
            lambda key: False,  # key is new
        )

        room = _make_room([_make_room_user('user-a')])
        self.router.set_room_resolver(
            lambda tenant, sender, recipient: room,
        )

        self.router.on_message(inbound)

        self.dao.room.add_message.assert_called_once()

    def test_on_message_no_idempotency_key_always_processes(self) -> None:
        inbound = self._make_inbound(metadata={})

        room = _make_room([_make_room_user('user-a')])
        self.router.set_room_resolver(
            lambda tenant, sender, recipient: room,
        )

        self.router.on_message(inbound)

        self.dao.room.add_message.assert_called_once()
