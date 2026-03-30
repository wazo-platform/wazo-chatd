# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from wazo_chatd.connectors.delivery import MAX_RETRIES, DeliveryStatus
from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.types import (
    ConnectorConfig,
    InboundMessage,
    OutboundMessage,
    RoomParticipant,
)
from wazo_chatd.database.async_helpers import _current_session


def _make_outbound(message_uuid: str = 'delivery-1') -> OutboundMessage:
    return OutboundMessage(
        room_uuid='room-uuid',
        message_uuid=message_uuid,
        sender_uuid='user-uuid',
        body='hello',
        sender_alias='+15551234',
        recipient_alias='+15559876',
        metadata={'idempotency_key': 'key-1'},
    )


class _FakeConnector:
    backend = 'twilio'
    supported_types = ('sms',)

    def __init__(self) -> None:
        self.send_return = 'ext-msg-id-123'
        self.send_side_effect: Exception | None = None

    def configure(self, type_, provider_config, connector_config) -> None:
        pass

    def send(self, message: OutboundMessage) -> str:
        if self.send_side_effect:
            raise self.send_side_effect
        return self.send_return


class TestDeliveryExecutorLoadFromPipe(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Mock()
        self.registry.get_backend.return_value = _FakeConnector
        self.executor = DeliveryExecutor(
            registry=self.registry,
            connector_config={},
            notifier=Mock(),
        )

    def test_load_config_creates_instances(self) -> None:
        config_sync = ConnectorConfig(
            providers=[
                {
                    'name': 'twilio-sms',
                    'type': 'sms',
                    'backend': 'twilio',
                    'configuration': {'account_sid': 'test'},
                },
            ]
        )

        self.executor.load_config(config_sync)

        assert 'twilio-sms' in self.executor.connectors
        self.registry.get_backend.assert_called_with('twilio')

    def test_load_config_multiple_providers(self) -> None:
        config_sync = ConnectorConfig(
            providers=[
                {
                    'name': 'twilio-sms',
                    'type': 'sms',
                    'backend': 'twilio',
                    'configuration': {},
                },
                {
                    'name': 'twilio-mms',
                    'type': 'mms',
                    'backend': 'twilio',
                    'configuration': {},
                },
            ]
        )

        self.executor.load_config(config_sync)

        assert len(self.executor.connectors) == 2


class TestDeliveryExecutorExecute(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.registry = Mock()
        self.connector = _FakeConnector()
        self.notifier = AsyncMock()
        self.executor = DeliveryExecutor(
            registry=self.registry,
            connector_config={},
            notifier=self.notifier,
        )
        self.executor.connectors['twilio-sms'] = self.connector  # type: ignore[assignment]

        self.delivery = Mock()
        self.delivery.message_uuid = 'delivery-1'
        self.delivery.backend = 'twilio'
        self.delivery.retry_count = 0
        self.delivery.external_id = None
        self.delivery.records = []
        self.delivery.message = None

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_execute_success(self) -> None:
        outbound = _make_outbound()

        await self.executor.execute(outbound, self.delivery)

        assert self.delivery.external_id == 'ext-msg-id-123'

    async def test_execute_failure_increments_retry(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')
        outbound = _make_outbound()

        await self.executor.execute(outbound, self.delivery)

        assert self.delivery.retry_count == 1

    async def test_execute_max_retries_sets_dead_letter(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')
        self.delivery.retry_count = MAX_RETRIES - 1
        outbound = _make_outbound()

        await self.executor.execute(outbound, self.delivery)

        statuses = [r.status for r in self.delivery.records]
        assert DeliveryStatus.DEAD_LETTER.value in statuses

    async def test_execute_publishes_status_event(self) -> None:
        outbound = _make_outbound()

        await self.executor.execute(outbound, self.delivery)

        self.notifier.delivery_status_updated.assert_awaited_once_with(self.delivery)


def _make_outbound_with_participants(
    external_identity: str = '+15559876',
) -> OutboundMessage:
    return OutboundMessage(
        room_uuid='room-uuid',
        message_uuid='msg-uuid',
        sender_uuid='user-uuid',
        body='hello',
        participants=(
            RoomParticipant(uuid='user-a', identity=None),
            RoomParticipant(uuid='ext-uuid', identity=external_identity),
        ),
        metadata={'idempotency_key': 'msg-uuid'},
    )


class TestDeliveryExecutorRouteOutbound(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.registry = Mock()
        self.registry.available_backends.return_value = ['twilio']
        backend_cls = Mock()
        backend_cls.supported_types = ('sms',)
        instance = Mock()
        instance.normalize_identity.return_value = '+15559876'
        backend_cls.return_value = instance
        self.registry.get_backend.return_value = backend_cls

        self.connector = _FakeConnector()
        self.executor = DeliveryExecutor(
            registry=self.registry,
            connector_config={},
            notifier=AsyncMock(),
        )
        self.executor.connectors['twilio-sms'] = self.connector  # type: ignore[assignment]

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_route_outbound_resolves_alias_and_enqueues(self) -> None:
        alias = Mock()
        alias.identity = '+15551234'
        alias.provider = Mock(backend='twilio')

        outbound = _make_outbound_with_participants()

        self.executor._user_alias_dao.list_by_user_and_types = AsyncMock(
            return_value=[alias]
        )

        await self.executor.route_outbound(outbound)

        self.session.flush.assert_awaited()

    async def test_route_outbound_internal_only_is_noop(self) -> None:
        outbound = OutboundMessage(
            room_uuid='room-uuid',
            message_uuid='msg-uuid',
            sender_uuid='user-uuid',
            body='hello',
            participants=(
                RoomParticipant(uuid='user-a', identity=None),
                RoomParticipant(uuid='user-b', identity=None),
            ),
        )

        await self.executor.route_outbound(outbound)

        self.session.add.assert_not_called()


def _make_inbound(
    idempotency_key: str | None = None,
) -> InboundMessage:
    metadata: dict[str, str] = {}
    if idempotency_key:
        metadata['idempotency_key'] = idempotency_key
    return InboundMessage(
        sender='+15559876',
        recipient='+15551234',
        body='hello from outside',
        backend='twilio',
        external_id='ext-123',
        metadata=metadata,
    )


class TestDeliveryExecutorRouteInbound(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.registry = Mock()
        self.notifier = AsyncMock()
        self.executor = DeliveryExecutor(
            registry=self.registry,
            connector_config={},
            notifier=self.notifier,
        )

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_route_inbound_dedup_skips_duplicate(self) -> None:
        inbound = _make_inbound(idempotency_key='existing-key')

        self.executor._room_dao.check_duplicate_idempotency_key = AsyncMock(
            return_value=True
        )

        await self.executor.route_inbound(inbound)

        self.session.add.assert_not_called()

    async def test_route_inbound_no_dedup_key_skips_dedup_check(self) -> None:
        inbound = _make_inbound()

        self.executor._room_dao.check_duplicate_idempotency_key = AsyncMock()
        self.executor._user_alias_dao.find_by_identity_and_backend = AsyncMock(
            return_value=None
        )

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.check_duplicate_idempotency_key.assert_not_awaited()

    async def test_route_inbound_unknown_recipient_logs_and_returns(self) -> None:
        inbound = _make_inbound()

        self.executor._user_alias_dao.find_by_identity_and_backend = AsyncMock(
            return_value=None
        )

        await self.executor.route_inbound(inbound)

        self.session.add.assert_not_called()

    async def test_route_inbound_creates_message_and_meta(self) -> None:
        alias = Mock()
        alias.user_uuid = 'wazo-user-uuid'
        alias.tenant_uuid = 'tenant-uuid'
        alias.provider = Mock(tenant_uuid='tenant-uuid')
        alias.user = Mock(uuid='wazo-user-uuid', wazo_uuid='wazo-system-uuid')

        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='wazo-user-uuid')]

        inbound = _make_inbound()

        self.executor._user_alias_dao.find_by_identity_and_backend = AsyncMock(
            return_value=alias
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock()
        self.executor._room_dao.add_message_meta = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.add_message.assert_awaited_once()
        self.executor._room_dao.add_message_meta.assert_awaited_once()

    async def test_route_inbound_publishes_message_event(self) -> None:
        alias = Mock()
        alias.user_uuid = 'wazo-user-uuid'
        alias.tenant_uuid = 'tenant-uuid'
        alias.provider = Mock(tenant_uuid='tenant-uuid')
        alias.user = Mock(uuid='wazo-user-uuid', wazo_uuid='wazo-system-uuid')

        room = Mock()
        room.uuid = 'room-uuid'
        room.tenant_uuid = 'tenant-uuid'
        room.users = [Mock(uuid='wazo-user-uuid')]

        inbound = _make_inbound()

        self.executor._user_alias_dao.find_by_identity_and_backend = AsyncMock(
            return_value=alias
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock()
        self.executor._room_dao.add_message_meta = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.notifier.message_created.assert_awaited_once()
