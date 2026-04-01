# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from wazo_chatd.connectors.delivery import MAX_RETRIES, DeliveryStatus
from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.store import ConnectorStore
from wazo_chatd.connectors.types import (
    InboundMessage,
    OutboundMessage,
    RoomParticipant,
    StatusUpdate,
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


class TestDeliveryExecutorExecute(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.registry = Mock()
        self.connector = _FakeConnector()
        self.notifier = AsyncMock()
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=self.registry,
            notifier=self.notifier,
            store=ConnectorStore(),
        )
        self.executor._store.register('twilio-sms', self.connector)

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

        added_records = [
            call.args[0]
            for call in self.session.add.call_args_list
            if hasattr(call.args[0], 'status')
        ]
        statuses = [r.status for r in added_records]
        assert DeliveryStatus.DEAD_LETTER.value in statuses

    async def test_execute_publishes_status_event(self) -> None:
        outbound = _make_outbound()

        await self.executor.execute(outbound, self.delivery)

        self.notifier.delivery_status_updated.assert_awaited_once()


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
        self.registry.resolve_reachable_types.return_value = {'sms'}

        self.connector = _FakeConnector()
        self.store = ConnectorStore()
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=self.registry,
            notifier=AsyncMock(),
            store=self.store,
        )
        self.store.register('twilio-sms', self.connector)

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_route_outbound_resolves_alias_and_enqueues(self) -> None:
        alias = Mock()
        alias.identity = '+15551234'
        alias.tenant_uuid = 'tenant-uuid'
        alias.provider = Mock(backend='twilio')

        meta = Mock()
        meta.message_uuid = 'msg-uuid'
        meta.extra = {}

        outbound = _make_outbound_with_participants()

        self.executor._user_alias_dao.list_by_user_and_types = AsyncMock(
            return_value=[alias]
        )
        self.executor._room_dao.get_message_meta = AsyncMock(
            return_value=meta
        )

        await self.executor.route_outbound(outbound)

        self.executor._room_dao.get_message_meta.assert_awaited_once()
        assert meta.type_ == 'sms'
        assert meta.backend == 'twilio'

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
            config={'uuid': 'test-wazo-uuid'},
            registry=self.registry,
            notifier=self.notifier,
            store=ConnectorStore(),
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


def _make_status_update(
    external_id: str = 'ext-123',
    status: str = 'delivered',
    backend: str = 'test',
    error_code: str = '',
) -> StatusUpdate:
    return StatusUpdate(
        external_id=external_id,
        status=status,
        backend=backend,
        error_code=error_code,
    )


class TestDeliveryExecutorRouteStatusUpdate(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.store = ConnectorStore()
        self.notifier = AsyncMock()
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=Mock(),
            notifier=self.notifier,
            store=self.store,
        )

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    def _register_connector(self, status_map: dict) -> None:
        connector = Mock()
        connector.backend = 'test'
        connector.status_map = status_map
        self.store.register('test-provider', connector)

    def _mock_meta(self) -> Mock:
        meta = Mock()
        meta.message_uuid = 'msg-uuid'
        meta.message = Mock()
        meta.message.room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        meta.message.room.users = [Mock(uuid='user-1')]
        self.executor._room_dao.get_message_meta_by_external_id = AsyncMock(
            return_value=meta
        )
        return meta

    async def test_creates_delivery_record(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})
        self._mock_meta()

        await self.executor.route_status_update(_make_status_update())

        record = self.session.add.call_args[0][0]
        assert record.status == 'delivered'

    async def test_ignores_unmapped_status(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})

        await self.executor.route_status_update(
            _make_status_update(status='queued')
        )

        self.session.add.assert_not_called()

    async def test_drops_when_no_connector(self) -> None:
        await self.executor.route_status_update(_make_status_update())

        self.session.add.assert_not_called()

    async def test_drops_when_no_meta(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})
        self.executor._room_dao.get_message_meta_by_external_id = AsyncMock(
            return_value=None
        )

        await self.executor.route_status_update(_make_status_update())

        self.session.add.assert_not_called()

    async def test_passes_error_code_as_reason(self) -> None:
        self._register_connector({'failed': DeliveryStatus.FAILED})
        self._mock_meta()

        await self.executor.route_status_update(
            _make_status_update(status='failed', error_code='30003')
        )

        record = self.session.add.call_args[0][0]
        assert record.reason == '30003'

    async def test_publishes_notification(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})
        self._mock_meta()

        await self.executor.route_status_update(_make_status_update())

        self.notifier.delivery_status_updated.assert_awaited_once()
