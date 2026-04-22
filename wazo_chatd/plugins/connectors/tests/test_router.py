# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
import uuid
from typing import ClassVar
from unittest.mock import Mock

import pytest

from wazo_chatd.plugin_helpers.dependencies import MessageContext
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorAuthException,
    ConnectorParseError,
    MessageIdentityRequiredException,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.router import ConnectorRouter
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    StatusUpdate,
    TransportData,
    WebhookData,
)


class _SmsConnector:
    backend: ClassVar[str] = 'twilio'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    @classmethod
    def normalize_identity(cls, raw_identity: str) -> str:
        if raw_identity.startswith('+'):
            return raw_identity
        raise ValueError(f'Not a phone number: {raw_identity}')

    @classmethod
    def can_handle(cls, data: TransportData) -> bool:
        return True

    @classmethod
    def on_event(cls, data: TransportData) -> InboundMessage | StatusUpdate | None:
        match data:
            case WebhookData(body=body) if body.get('Body'):
                return InboundMessage(
                    sender=body.get('From', ''),
                    recipient=body.get('To', ''),
                    body=body['Body'],
                    backend=cls.backend,
                    message_type='sms',
                    external_id=body.get('MessageSid', ''),
                )
            case _:
                return None


class _EmailConnector:
    backend: ClassVar[str] = 'mailgun'
    supported_types: ClassVar[tuple[str, ...]] = ('email',)

    @classmethod
    def normalize_identity(cls, raw_identity: str) -> str:
        if '@' in raw_identity:
            return raw_identity.lower()
        raise ValueError(f'Not an email: {raw_identity}')

    @classmethod
    def can_handle(cls, data: TransportData) -> bool:
        match data:
            case WebhookData(body=body):
                return 'X-Mailgun-Signature' in body
            case _:
                return False

    @classmethod
    def on_event(cls, data: TransportData) -> InboundMessage | StatusUpdate | None:
        return None


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


def _build_router(
    config: dict | None = None,
    registry: ConnectorRegistry | None = None,
    service: Mock | None = None,
    auth_client: Mock | None = None,
    dao: Mock | None = None,
) -> ConnectorRouter:
    with unittest.mock.patch('wazo_chatd.plugins.connectors.router.DeliveryRunner'):
        return ConnectorRouter(
            config=config or {},
            registry=registry or ConnectorRegistry(),
            service=service or Mock(),
            auth_client=auth_client or Mock(),
            dao=dao or Mock(),
        )


class TestConnectorRouterDispatchWebhook(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        self.dao = Mock()
        self.dao.user_identity.find_tenant_by_identity.return_value = 'tenant-uuid'
        self.dao.room.find_tenant_by_external_id.return_value = 'tenant-uuid'
        self.router = _build_router(registry=self.registry, dao=self.dao)
        instance = Mock()
        instance.verify_signature.return_value = True
        self.router._store = Mock()
        self.router._store.find_by_backend.return_value = instance
        self.manager = self.router._delivery_runner

    def test_dispatch_enqueues_inbound_message(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-123'}
        )

        self.router.dispatch_webhook(data, backend='twilio')

        self.manager.enqueue_message.assert_called_once()
        result = self.manager.enqueue_message.call_args[0][0]
        assert isinstance(result, InboundMessage)
        assert result.body == 'hello'

    def test_dispatch_without_backend_hint(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hi', 'MessageSid': 'msg-1'}
        )

        self.router.dispatch_webhook(data)

        self.manager.enqueue_message.assert_called_once()

    def test_dispatch_skips_connector_that_cannot_handle(self) -> None:
        self.registry.register_backend(_EmailConnector)  # type: ignore[arg-type]
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-1'}
        )

        self.router.dispatch_webhook(data)

        self.manager.enqueue_message.assert_called_once()
        result = self.manager.enqueue_message.call_args[0][0]
        assert result.backend == 'twilio'

    def test_dispatch_skips_none_events(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(body={'no_body_or_status': True})

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(data)

        self.manager.enqueue_message.assert_not_called()

    def test_dispatch_no_backends_raises(self) -> None:
        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(WebhookData(body={}))

    def test_dispatch_falls_back_to_non_hint_connectors(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-1'}
        )

        self.router.dispatch_webhook(data, backend='vonage')

        self.manager.enqueue_message.assert_called_once()
        result = self.manager.enqueue_message.call_args[0][0]
        assert result.backend == 'twilio'


class TestConnectorRouterWebhookVerify(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        self.dao = Mock()
        self.dao.user_identity.find_tenant_by_identity.return_value = 'tenant-uuid'
        self.dao.room.find_tenant_by_external_id.return_value = 'tenant-uuid'

        self.instance = Mock()
        self.instance.verify_signature.return_value = True

        self.router = _build_router(registry=self.registry, dao=self.dao)
        self.router._store = Mock()
        self.router._store.find_by_backend.return_value = self.instance
        self.manager = self.router._delivery_runner

    def _webhook(self) -> WebhookData:
        return WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-1'}
        )

    def test_valid_signature_resolves_tenant_by_recipient_and_enqueues(self) -> None:
        data = WebhookData(
            body={
                'From': '+15559876',
                'To': '+15551234',
                'Body': 'hi',
                'MessageSid': 'msg-1',
            }
        )

        self.router.dispatch_webhook(data, backend='twilio')

        self.dao.user_identity.find_tenant_by_identity.assert_called_once_with(
            '+15551234', 'twilio'
        )
        self.router._store.find_by_backend.assert_called_once_with(
            'twilio', 'tenant-uuid'
        )
        self.instance.verify_signature.assert_called_once_with(data)
        self.manager.enqueue_message.assert_called_once()

    def test_invalid_signature_raises_401_and_skips_enqueue(self) -> None:
        self.instance.verify_signature.return_value = False

        with pytest.raises(ConnectorAuthException):
            self.router.dispatch_webhook(self._webhook(), backend='twilio')

        self.manager.enqueue_message.assert_not_called()

    def test_unknown_recipient_raises_parse_error(self) -> None:
        self.dao.user_identity.find_tenant_by_identity.return_value = None

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(self._webhook(), backend='twilio')

        self.manager.enqueue_message.assert_not_called()

    def test_store_cache_miss_raises_parse_error(self) -> None:
        self.router._store.find_by_backend.return_value = None

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(self._webhook(), backend='twilio')

        self.manager.enqueue_message.assert_not_called()


class TestConnectorRouterValidateOutbound(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.service = Mock()
        self.router = _build_router(registry=self.registry, service=self.service)

    def test_internal_room_without_sender_identity_uuid_passes(self) -> None:
        room = _make_room([_make_room_user('user-a'), _make_room_user('user-b')])
        ctx = MessageContext(room, Mock(), sender_identity_uuid=None)

        self.router.prepare_outbound(ctx)

        self.service.validate_identity_reachability.assert_not_called()

    def test_external_room_without_sender_identity_uuid_raises_409(self) -> None:
        room = _make_room(
            [
                _make_room_user('user-a'),
                _make_room_user('ext-uuid', identity='+15559876'),
            ]
        )
        ctx = MessageContext(room, Mock(), sender_identity_uuid=None)

        with pytest.raises(MessageIdentityRequiredException):
            self.router.prepare_outbound(ctx)

    def test_sender_identity_uuid_validates_and_prepares_delivery(self) -> None:
        room = _make_room([_make_room_user('user-a'), _make_room_user('user-b')])
        identity_uuid = uuid.uuid4()
        identity = Mock()
        self.service.validate_identity_reachability.return_value = identity
        message = Mock(user_uuid='user-a')
        ctx = MessageContext(room, message, sender_identity_uuid=identity_uuid)

        self.router.prepare_outbound(ctx)

        self.service.validate_identity_reachability.assert_called_once_with(
            room, 'user-a', identity_uuid
        )
        self.service.prepare_outbound_delivery.assert_called_once_with(
            message, identity
        )
        assert ctx.resolved_sender_identity is identity


class TestConnectorRouterValidateRoomCreation(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.service = Mock()
        self.router = _build_router(registry=self.registry, service=self.service)

    def test_delegates_to_service(self) -> None:
        room = _make_room([_make_room_user('user-a'), _make_room_user('user-b')])

        self.router.validate_room_creation(room)

        self.service.validate_room_reachability.assert_called_once_with(room)
