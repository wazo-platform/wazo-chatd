# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
import uuid
from typing import ClassVar
from unittest.mock import Mock

import pytest

from wazo_chatd.plugin_helpers.dependencies import MessageContext
from wazo_chatd.plugins.connectors.connector import ProviderIdentity
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorAuthException,
    ConnectorParseError,
    InventoryNotSupportedException,
    MessageIdentityRequiredException,
    NoSuchConnectorException,
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
    backend: ClassVar[str] = 'sms_backend'
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
            registry=registry if registry is not None else _build_registry(),
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
        self.router._store.find.return_value = instance
        self.manager = self.router._delivery_runner = Mock()

    def test_dispatch_enqueues_inbound_message(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-123'}
        )

        self.router.dispatch_webhook(data, backend='sms_backend')

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
        assert result.backend == 'sms_backend'

    def test_dispatch_skips_buggy_can_handle_and_tries_next(self) -> None:
        class _BuggyConnector:
            backend: ClassVar[str] = 'buggy'
            supported_types: ClassVar[tuple[str, ...]] = ('sms',)

            @classmethod
            def normalize_identity(cls, raw_identity: str) -> str:
                return raw_identity

            @classmethod
            def can_handle(cls, data: TransportData) -> bool:
                raise RuntimeError('backend explodes')

            @classmethod
            def on_event(
                cls, data: TransportData
            ) -> InboundMessage | StatusUpdate | None:
                return None

        self.registry.register_backend(_BuggyConnector)  # type: ignore[arg-type]
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-1'}
        )

        self.router.dispatch_webhook(data)

        self.manager.enqueue_message.assert_called_once()
        result = self.manager.enqueue_message.call_args[0][0]
        assert result.backend == 'sms_backend'

    def test_dispatch_skips_none_events(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(body={'no_body_or_status': True})

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(data)

        self.manager.enqueue_message.assert_not_called()

    def test_dispatch_no_backends_raises(self) -> None:
        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(WebhookData(body={}))

    def test_dispatch_unknown_backend_hint_raises(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-1'}
        )

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(data, backend='vonage')

        self.manager.enqueue_message.assert_not_called()

    def test_dispatch_hint_restricts_to_that_backend(self) -> None:
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        self.registry.register_backend(_EmailConnector)  # type: ignore[arg-type]
        data = WebhookData(
            body={'From': '+15559876', 'Body': 'hello', 'MessageSid': 'msg-1'}
        )

        self.router.dispatch_webhook(data, backend='sms_backend')

        result = self.manager.enqueue_message.call_args[0][0]
        assert result.backend == 'sms_backend'


class TestConnectorRouterWebhookVerify(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        self.registry.register_backend(_SmsConnector)  # type: ignore[arg-type]
        self.dao = Mock()
        self.dao.user_identity.find_tenant_by_identity.return_value = 'tenant-uuid'
        self.dao.room.find_tenant_by_external_id.return_value = 'tenant-uuid'

        self.instance = Mock()
        self.instance.verifies_signatures = True
        self.instance.verify_signature.return_value = True

        self.router = _build_router(registry=self.registry, dao=self.dao)
        self.router._store = Mock()
        self.router._store.get.return_value = self.instance
        self.manager = self.router._delivery_runner = Mock()

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

        self.router.dispatch_webhook(data, backend='sms_backend')

        self.dao.user_identity.find_tenant_by_identity.assert_called_once_with(
            '+15551234', 'sms_backend'
        )
        self.router._store.get.assert_called_once_with('sms_backend', 'tenant-uuid')
        self.instance.verify_signature.assert_called_once_with(data)
        self.manager.enqueue_message.assert_called_once()

    def test_invalid_signature_raises_401_and_skips_enqueue(self) -> None:
        self.instance.verify_signature.return_value = False

        with pytest.raises(ConnectorAuthException):
            self.router.dispatch_webhook(self._webhook(), backend='sms_backend')

        self.manager.enqueue_message.assert_not_called()

    def test_unknown_recipient_raises_parse_error(self) -> None:
        self.dao.user_identity.find_tenant_by_identity.return_value = None

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(self._webhook(), backend='sms_backend')

        self.manager.enqueue_message.assert_not_called()

    def test_unknown_backend_raises_parse_error(self) -> None:
        from wazo_chatd.plugins.connectors.exceptions import (
            BackendNotConfiguredException,
        )

        self.router._store.get.side_effect = BackendNotConfiguredException(
            'sms_backend', 'tenant-uuid'
        )

        with pytest.raises(ConnectorParseError):
            self.router.dispatch_webhook(self._webhook(), backend='sms_backend')

        self.manager.enqueue_message.assert_not_called()

    def test_auth_unavailable_raises_transient_error(self) -> None:
        from wazo_chatd.plugins.connectors.exceptions import (
            AuthServiceUnavailableException,
            ConnectorTransientError,
        )

        self.router._store.get.side_effect = AuthServiceUnavailableException()

        with pytest.raises(ConnectorTransientError):
            self.router.dispatch_webhook(self._webhook(), backend='sms_backend')

        self.manager.enqueue_message.assert_not_called()

    def test_verifies_signatures_false_skips_check(self) -> None:
        instance = Mock()
        instance.verifies_signatures = False
        self.router._store.get.return_value = instance

        self.router.dispatch_webhook(self._webhook(), backend='sms_backend')

        instance.verify_signature.assert_not_called()
        self.manager.enqueue_message.assert_called_once()


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
            room, message, identity
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


class TestConnectorRouterValidateTenantBackend(unittest.TestCase):
    def setUp(self) -> None:
        self.router = _build_router()
        self.router._store = Mock()

    def test_delegates_to_store_get(self) -> None:
        self.router.validate_tenant_backend('tenant-uuid', 'sms_backend')

        self.router._store.get.assert_called_once_with('sms_backend', 'tenant-uuid')

    def test_propagates_get_exceptions(self) -> None:
        self.router._store.get.side_effect = RuntimeError('boom')

        with self.assertRaises(RuntimeError):
            self.router.validate_tenant_backend('tenant-uuid', 'sms_backend')


class TestConnectorRouterReconcileTenantBackend(unittest.TestCase):
    def setUp(self) -> None:
        self.dao = Mock()
        self.router = _build_router(dao=self.dao)
        self.router._store = Mock()
        self.router._listener_runner = Mock()

    def test_drops_when_no_identity_and_store_has_entry(self) -> None:
        self.dao.user_identity.has_identities_for_backend.return_value = False
        self.router._store.peek.return_value = Mock()

        self.router.reconcile_tenant_backend('tenant-uuid', 'sms_backend')

        self.router._store.drop.assert_called_once_with('sms_backend', 'tenant-uuid')

    def test_noop_when_no_identity_and_store_empty(self) -> None:
        self.dao.user_identity.has_identities_for_backend.return_value = False
        self.router._store.peek.return_value = None

        self.router.reconcile_tenant_backend('tenant-uuid', 'sms_backend')

        self.router._store.drop.assert_not_called()

    def test_noop_when_identity_exists(self) -> None:
        self.dao.user_identity.has_identities_for_backend.return_value = True
        self.router._store.peek.return_value = Mock()

        self.router.reconcile_tenant_backend('tenant-uuid', 'sms_backend')

        self.router._store.drop.assert_not_called()

    def test_always_resyncs_pollers_and_listeners(self) -> None:
        self.dao.user_identity.has_identities_for_backend.return_value = False
        self.router._store.peek.return_value = None

        self.router.reconcile_tenant_backend('tenant-uuid', 'sms_backend')

        self.router._delivery_runner.resync_pollers.assert_called_once()
        self.router._listener_runner.resync.assert_called_once()


class TestConnectorRouterEmptyRegistry(unittest.TestCase):
    def test_empty_registry_skips_runner_construction(self) -> None:
        with (
            unittest.mock.patch(
                'wazo_chatd.plugins.connectors.router.DeliveryRunner'
            ) as delivery_mock,
            unittest.mock.patch(
                'wazo_chatd.plugins.connectors.router.ListenerRunner'
            ) as listener_mock,
        ):
            router = ConnectorRouter(
                config={},
                registry=ConnectorRegistry(),
                service=Mock(),
                auth_client=Mock(),
                dao=Mock(),
            )

            delivery_mock.assert_not_called()
            listener_mock.assert_not_called()
            assert router._delivery_runner is router._listener_runner

    def test_empty_registry_lifecycle_methods_do_not_raise(self) -> None:
        router = _build_router(registry=ConnectorRegistry())

        router.start()
        router.stop()
        router.reconcile_tenant_backend('tenant-uuid', 'sms_backend')

    def test_empty_registry_provide_status_reports_ok(self) -> None:
        router = _build_router(registry=ConnectorRegistry())
        router._store = Mock()
        router._store.__len__ = Mock(return_value=0)

        status: dict = {}
        router.provide_status(status)

        assert status['connectors']['status'] == 'ok'
        assert status['connectors']['in_flight'] == 0
        assert status['connectors']['backends_registered'] == 0

    def test_non_empty_registry_constructs_runners(self) -> None:
        with (
            unittest.mock.patch(
                'wazo_chatd.plugins.connectors.router.DeliveryRunner'
            ) as delivery_mock,
            unittest.mock.patch(
                'wazo_chatd.plugins.connectors.router.ListenerRunner'
            ) as listener_mock,
        ):
            router = ConnectorRouter(
                config={},
                registry=_build_registry(),
                service=Mock(),
                auth_client=Mock(),
                dao=Mock(),
            )

            delivery_mock.assert_called_once()
            listener_mock.assert_called_once()
            assert router._delivery_runner is not router._listener_runner


class TestConnectorRouterListConnectorInventory(unittest.TestCase):
    def setUp(self) -> None:
        self.dao = Mock()
        self.dao.user_identity.list_.return_value = []
        self.router = _build_router(dao=self.dao)
        self.router._store = Mock()

    def test_unknown_backend_raises_no_such_connector(self) -> None:
        with pytest.raises(NoSuchConnectorException):
            self.router.list_connector_inventory('tenant-uuid', 'nonexistent')

    def test_backend_without_capability_raises_inventory_not_supported(self) -> None:
        connector = Mock()
        connector.list_provider_identities.side_effect = NotImplementedError()
        self.router._store.get.return_value = connector

        with pytest.raises(InventoryNotSupportedException):
            self.router.list_connector_inventory('tenant-uuid', 'sms_backend')

    def test_returns_provider_identities_with_null_binding_when_unbound(self) -> None:
        connector = Mock()
        connector.list_provider_identities.return_value = [
            ProviderIdentity(identity='+15551234', type='sms'),
        ]
        self.router._store.get.return_value = connector

        result = self.router.list_connector_inventory('tenant-uuid', 'sms_backend')

        assert result == [
            {'identity': '+15551234', 'type_': 'sms', 'binding': None},
        ]

    def test_returns_provider_identities_with_binding_when_bound(self) -> None:
        connector = Mock()
        connector.list_provider_identities.return_value = [
            ProviderIdentity(identity='+15551234', type='sms'),
            ProviderIdentity(identity='+15555678', type='sms'),
        ]
        self.router._store.get.return_value = connector

        bound = Mock()
        bound.identity = '+15551234'
        bound.uuid = uuid.UUID('00000000-0000-0000-0000-000000000001')
        bound.user_uuid = uuid.UUID('00000000-0000-0000-0000-000000000002')
        self.dao.user_identity.list_.return_value = [bound]

        result = self.router.list_connector_inventory('tenant-uuid', 'sms_backend')

        assert result == [
            {
                'identity': '+15551234',
                'type_': 'sms',
                'binding': {
                    'uuid': str(bound.uuid),
                    'user_uuid': str(bound.user_uuid),
                },
            },
            {'identity': '+15555678', 'type_': 'sms', 'binding': None},
        ]

    def test_binding_query_scoped_to_tenant_and_backend(self) -> None:
        connector = Mock()
        connector.list_provider_identities.return_value = []
        self.router._store.get.return_value = connector

        self.router.list_connector_inventory('tenant-uuid', 'sms_backend')

        self.dao.user_identity.list_.assert_called_once_with(
            tenant_uuids=['tenant-uuid'], backends=['sms_backend']
        )
