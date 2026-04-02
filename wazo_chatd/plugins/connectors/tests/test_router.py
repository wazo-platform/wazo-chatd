# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import Mock

import pytest

from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorParseError,
    MessageAliasRequiredError,
    UnreachableParticipantError,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.router import ConnectorRouter
from wazo_chatd.plugins.connectors.types import InboundMessage, WebhookData


class _SmsConnector:
    backend: ClassVar[str] = 'twilio'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    def configure(self, type_, provider_config, connector_config) -> None:
        pass

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


class TestConnectorRouterDispatchWebhook(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryLoop'):
            self.router = ConnectorRouter(config={}, registry=self.registry, dao=Mock())
        self.manager = self.router._delivery_loop

    def _make_connector(self, backend: str = 'twilio', can_handle: bool = True) -> Mock:
        connector = Mock()
        connector.backend = backend
        connector.can_handle.return_value = can_handle
        return connector

    def test_dispatch_enqueues_inbound_message(self) -> None:
        connector = self._make_connector()
        inbound = InboundMessage(
            sender='+15559876',
            recipient='+15551234',
            body='hello',
            backend='twilio',
            external_id='msg-123',
        )
        connector.on_event.return_value = inbound
        self.router.add_instance('twilio-sms', connector)

        self.router.dispatch_webhook(
            WebhookData(body={'From': '+15559876'}), backend='twilio'
        )

        connector.can_handle.assert_called_once()
        connector.on_event.assert_called_once()
        self.manager.enqueue_message.assert_called_once_with(inbound)

    def test_dispatch_without_backend_hint(self) -> None:
        connector = self._make_connector()
        inbound = InboundMessage(
            sender='+15559876',
            recipient='+15551234',
            body='hello',
            backend='twilio',
            external_id='msg-123',
        )
        connector.on_event.return_value = inbound
        self.router.add_instance('twilio-sms', connector)

        self.router.dispatch_webhook(WebhookData(body={'From': '+15559876'}))

        self.manager.enqueue_message.assert_called_once_with(inbound)

    def test_dispatch_skips_connector_that_cannot_handle(self) -> None:
        skipped = self._make_connector(can_handle=False)
        skipped.on_event.return_value = None

        handler = self._make_connector()
        inbound = InboundMessage(
            sender='+15559876',
            recipient='+15551234',
            body='hello',
            backend='twilio',
            external_id='msg-123',
        )
        handler.on_event.return_value = inbound

        self.router.add_instance('skipped', skipped)
        self.router.add_instance('handler', handler)

        self.router.dispatch_webhook(WebhookData(body={'From': '+15559876'}))

        skipped.on_event.assert_not_called()
        self.manager.enqueue_message.assert_called_once_with(inbound)

    def test_dispatch_skips_none_events(self) -> None:
        connector = self._make_connector()
        connector.on_event.return_value = None
        self.router.add_instance('twilio-sms', connector)

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(WebhookData(body={'status': 'delivered'}))

        self.manager.enqueue_message.assert_not_called()

    def test_dispatch_no_instances_raises(self) -> None:
        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(WebhookData(body={}))

    def test_dispatch_falls_back_to_non_hint_connectors(self) -> None:
        vonage = self._make_connector(backend='vonage')
        inbound = InboundMessage(
            sender='+15559876',
            recipient='+15551234',
            body='hello',
            backend='vonage',
            external_id='msg-789',
        )
        vonage.on_event.return_value = inbound
        self.router.add_instance('vonage-sms', vonage)

        self.router.dispatch_webhook(
            WebhookData(body={'data': 'test'}), backend='twilio'
        )

        self.manager.enqueue_message.assert_called_once_with(inbound)

    def test_dispatch_tries_all_instances(self) -> None:
        connector_a = self._make_connector()
        connector_a.on_event.return_value = None

        connector_b = self._make_connector()
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

        self.router.dispatch_webhook(WebhookData(body={'data': 'test'}))

        self.manager.enqueue_message.assert_called_once_with(inbound)


class TestConnectorRouterSend(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryLoop'):
            self.router = ConnectorRouter(config={}, registry=self.registry, dao=Mock())
        self.manager = self.router._delivery_loop

    def test_send_internal_room_is_noop(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('user-b'),
            ]
        )
        room.uuid = 'room-uuid'
        message = Mock(uuid='msg-uuid', user_uuid='user-a', content='hi')

        self.router.send(room, message)

        self.manager.enqueue_message.assert_not_called()

    @unittest.mock.patch(
        'wazo_chatd.plugins.connectors.router.register_post_commit_callback',
        side_effect=lambda cb: cb(),
    )
    def test_send_external_room_enqueues_with_participants(self, _) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        room.uuid = 'room-uuid'
        message = Mock(uuid='msg-uuid', user_uuid='user-a', content='hello')

        self.router.send(room, message)

        self.manager.enqueue_message.assert_called_once()
        outbound = self.manager.enqueue_message.call_args[0][0]
        assert outbound.room_uuid == 'room-uuid'
        assert outbound.message_uuid == 'msg-uuid'
        assert outbound.sender_uuid == 'user-a'
        assert outbound.body == 'hello'
        assert len(outbound.participants) == 2
        external = [p for p in outbound.participants if p.identity]
        assert len(external) == 1
        assert external[0].identity == '+15559876'


class TestConnectorRouterOnRoomMessageCreated(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryLoop'):
            self.router = ConnectorRouter(config={}, registry=self.registry, dao=Mock())
        self.router.send = Mock()  # type: ignore[assignment]

    def test_unpacks_event_and_calls_send(self) -> None:
        room = _make_room()
        message = Mock()

        self.router.on_room_message_created((room, message))

        self.router.send.assert_called_once_with(room, message)


class TestConnectorRouterValidateOutbound(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryLoop'):
            self.router = ConnectorRouter(config={}, registry=self.registry, dao=Mock())

    def test_internal_room_without_alias_passes(self) -> None:
        room = _make_room(
            [_make_room_user('user-a'), _make_room_user('user-b')]
        )
        message = Mock(alias=None)

        self.router.validate_outbound((room, message))

    def test_external_room_with_alias_passes(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        message = Mock(alias='John')

        self.router.validate_outbound((room, message))

    def test_external_room_without_alias_raises_409(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        message = Mock(alias=None)

        with pytest.raises(MessageAliasRequiredError):
            self.router.validate_outbound((room, message))

    def test_external_room_with_empty_alias_raises_409(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        message = Mock(alias='')

        with pytest.raises(MessageAliasRequiredError):
            self.router.validate_outbound((room, message))


class TestConnectorRouterValidateRoomCreation(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryLoop'):
            self.router = ConnectorRouter(
                config={}, registry=self.registry, dao=Mock()
            )

    def test_internal_only_room_passes(self) -> None:
        room = _make_room(
            [_make_room_user('user-a'), _make_room_user('user-b')]
        )

        self.router.validate_room_creation(room)

    def test_external_participant_reachable_passes(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )

        self.router.validate_room_creation(room)

    def test_external_participant_unreachable_raises_409(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='not-a-phone-or-email'),
            ]
        )

        with pytest.raises(UnreachableParticipantError):
            self.router.validate_room_creation(room)

    def test_multiple_external_one_unreachable_raises_409(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-1', identity='+15559876'),
                _make_room_user('ext-2', identity='not-reachable'),
            ]
        )

        with pytest.raises(UnreachableParticipantError):
            self.router.validate_room_creation(room)


class TestConnectorRouterLoadProviders(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        self.registry.register_backend(_SmsConnector)
        self.dao = Mock()
        with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryLoop'):
            self.router = ConnectorRouter(
                config={'connectors': {'twilio': {'mode': 'webhook'}}},
                registry=self.registry,
                dao=self.dao,
            )

    def _make_provider(
        self,
        name: str = 'my-provider',
        type_: str = 'sms',
        backend: str = 'twilio',
        configuration: dict | None = None,
    ) -> Mock:
        provider = Mock()
        provider.name = name
        provider.type_ = type_
        provider.backend = backend
        provider.configuration = configuration or {}
        return provider

    def test_loads_single_provider(self) -> None:
        self.dao.provider.list_.return_value = [self._make_provider()]

        self.router.load_providers()

        assert len(self.router._store) == 1

    def test_loads_multiple_providers(self) -> None:
        self.dao.provider.list_.return_value = [
            self._make_provider(name='provider-a'),
            self._make_provider(name='provider-b'),
        ]

        self.router.load_providers()

        assert len(self.router._store) == 2

    def test_skips_unknown_backend(self) -> None:
        self.dao.provider.list_.return_value = [
            self._make_provider(backend='nonexistent'),
        ]

        self.router.load_providers()

        assert len(self.router._store) == 0

    def test_replaces_previous_instances(self) -> None:
        self.dao.provider.list_.return_value = [self._make_provider()]
        self.router.load_providers()
        assert len(self.router._store) == 1

        self.dao.provider.list_.return_value = []
        self.router.load_providers()
        assert len(self.router._store) == 0

    def test_passes_connector_config_to_configure(self) -> None:
        provider = self._make_provider(configuration={'api_key': 'secret'})
        self.dao.provider.list_.return_value = [provider]

        self.router.load_providers()

        instance = self.router._store.find_by_backend('twilio')
        assert instance is not None

    def test_handles_none_configuration(self) -> None:
        provider = self._make_provider(configuration=None)
        self.dao.provider.list_.return_value = [provider]

        self.router.load_providers()

        assert len(self.router._store) == 1
