# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
import unittest
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, ClassVar
from unittest.mock import AsyncMock, Mock

import pytest

from wazo_chatd.database.async_helpers import _current_session
from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.exceptions import DuplicateExternalIdException
from wazo_chatd.plugins.connectors.exceptions import ConnectorSendError
from wazo_chatd.plugins.connectors.executor import (
    INBOUND_RETRY_DELAYS,
    OUTBOUND_MAX_RETRIES,
    DeliveryExecutor,
    generate_message_signature,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
    TransportData,
)

FIXED_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _mock_add_delivery_record() -> AsyncMock:
    async def _side_effect(record):
        record.timestamp = FIXED_NOW
        return record

    return AsyncMock(side_effect=_side_effect)


def _make_outbound(message_uuid: str = 'delivery-1') -> OutboundMessage:
    return OutboundMessage(
        room_uuid='room-uuid',
        message_uuid=message_uuid,
        sender_uuid='user-uuid',
        body='hello',
        message_type='sms',
        sender_identity='+15551234',
        recipient_identity='+15559876',
        metadata={'idempotency_key': 'key-1'},
    )


class _FakeConnector:
    backend: ClassVar[str] = 'sms_backend'
    supported_types: ClassVar[tuple[str, ...]] = ('sms',)
    status_map: ClassVar[dict[str, DeliveryStatus]] = {}

    def __init__(
        self,
        provider_config: Mapping[str, Any] | None = None,
        connector_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.send_return = 'ext-msg-id-123'
        self.send_side_effect: Exception | None = None

    def send(self, message: OutboundMessage) -> str:
        if self.send_side_effect:
            raise self.send_side_effect
        return self.send_return

    @classmethod
    def can_handle(cls, data: TransportData) -> bool:
        return True

    @classmethod
    def on_event(cls, data: TransportData) -> InboundMessage | StatusUpdate | None:
        return None

    def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
        pass

    def stop(self) -> None:
        pass

    @classmethod
    def normalize_identity(cls, raw_identity: str) -> str:
        return raw_identity


class TestDeliveryExecutorOutboundSend(unittest.IsolatedAsyncioTestCase):
    """Covers the send + record-outcome path of route_outbound.

    Tests build a fully-resolved meta (with recipient identity already
    known) so they exercise the connector dispatch + retry decision in
    isolation from the recipient-resolution code path.
    """

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
            store=ConnectorStore(Mock(), ConnectorRegistry()),
        )
        self.executor._store._cache[('tenant-uuid', 'sms_backend')] = self.connector  # type: ignore[assignment]
        self.executor._store._expires_at[('tenant-uuid', 'sms_backend')] = (
            time.monotonic() + 300.0
        )
        self.executor._room_dao.add_delivery_record = _mock_add_delivery_record()

        sender_record = Mock(
            identity='+15551234',
            tenant_uuid='tenant-uuid',
            backend='sms_backend',
            type_='sms',
        )
        recipient_user = Mock(uuid='recipient-uuid', identity='+15559876')
        sender_user = Mock(uuid='sender-uuid', identity=None)
        room = Mock(uuid='room-uuid', users=[sender_user, recipient_user])
        message = Mock(uuid='msg-uuid', user_uuid='sender-uuid', content='hello')
        message.room = room

        self.delivery = Mock()
        self.delivery.message_uuid = 'delivery-1'
        self.delivery.backend = 'sms_backend'
        self.delivery.retry_count = 0
        self.delivery.external_id = None
        self.delivery.records = []
        self.delivery.sender_identity = sender_record
        self.delivery.message = message
        self.delivery.extra = {}

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_success_writes_external_id(self) -> None:
        await self.executor.route_outbound(self.delivery)

        assert self.delivery.external_id == 'ext-msg-id-123'

    async def test_success_writes_accepted_only(self) -> None:
        await self.executor.route_outbound(self.delivery)

        dao_mock = self.executor._room_dao.add_delivery_record
        statuses = [call.args[0].status for call in dao_mock.call_args_list]
        assert statuses == [DeliveryStatus.ACCEPTED.value]

    async def test_failure_increments_retry(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')

        await self.executor.route_outbound(self.delivery)

        assert self.delivery.retry_count == 1

    async def test_max_retries_sets_dead_letter(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')
        self.delivery.retry_count = OUTBOUND_MAX_RETRIES - 1

        await self.executor.route_outbound(self.delivery)

        dao_mock = self.executor._room_dao.add_delivery_record
        statuses = [call.args[0].status for call in dao_mock.call_args_list]
        assert DeliveryStatus.DEAD_LETTER.value in statuses

    async def test_publishes_status_event(self) -> None:
        await self.executor.route_outbound(self.delivery)

        self.notifier.delivery_status_updated.assert_awaited_once()

    async def test_unexpected_error_treated_as_failure(self) -> None:
        self.connector.send_side_effect = RuntimeError('SDK crashed')

        await self.executor.route_outbound(self.delivery)

        assert self.delivery.retry_count == 1
        dao_mock = self.executor._room_dao.add_delivery_record
        statuses = [call.args[0].status for call in dao_mock.call_args_list]
        assert DeliveryStatus.RETRYING.value in statuses

    async def test_success_returns_no_retry(self) -> None:
        result = await self.executor.route_outbound(self.delivery)

        assert result is None

    async def test_retrying_returns_next_retry_delay(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')

        result = await self.executor.route_outbound(self.delivery)

        assert result == 30.0

    async def test_dead_letter_returns_no_retry(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')
        self.delivery.retry_count = OUTBOUND_MAX_RETRIES - 1

        result = await self.executor.route_outbound(self.delivery)

        assert result is None


class TestDeliveryExecutorRouteOutbound(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.registry = Mock()
        self.registry.resolve_reachable_types.return_value = {'sms'}

        self.connector = _FakeConnector()
        self.store = ConnectorStore(Mock(), ConnectorRegistry())
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=self.registry,
            notifier=AsyncMock(),
            store=self.store,
        )
        self.store._cache[('tenant-uuid', 'sms_backend')] = self.connector  # type: ignore[assignment]
        self.store._expires_at[('tenant-uuid', 'sms_backend')] = (
            time.monotonic() + 300.0
        )
        self.executor._room_dao.add_delivery_record = _mock_add_delivery_record()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_route_outbound_resolves_identity_and_sends(self) -> None:
        sender_identity = Mock(
            identity='+15551234',
            tenant_uuid='tenant-uuid',
            backend='sms_backend',
            type_='sms',
        )
        recipient_user = Mock(uuid='recipient-uuid', identity=None)
        sender_user = Mock(uuid='sender-uuid', identity=None)
        room = Mock(uuid='room-uuid', users=[sender_user, recipient_user])
        message = Mock(uuid='msg-uuid', user_uuid='sender-uuid', content='hello')

        meta = Mock()
        meta.message_uuid = 'msg-uuid'
        meta.sender_identity = sender_identity
        meta.message = message
        meta.message.room = room
        meta.extra = {}

        recipient_identity = Mock(identity='+15559876')
        self.executor._user_identity_dao.list_by_user = AsyncMock(
            return_value=[recipient_identity]
        )

        await self.executor.route_outbound(meta)

        assert meta.extra['outbound_idempotency_key'] == 'msg-uuid'


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
        backend='sms_backend',
        message_type='sms',
        external_id='ext-123',
        metadata=metadata,
    )


class TestDeliveryExecutorRouteInbound(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)

        self.registry = Mock()
        self.registry.get_backend.side_effect = KeyError
        self.notifier = AsyncMock()
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=self.registry,
            notifier=self.notifier,
            store=ConnectorStore(Mock(), ConnectorRegistry()),
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
        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={}
        )

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.check_duplicate_idempotency_key.assert_not_awaited()

    async def test_route_inbound_unknown_recipient_logs_and_returns(self) -> None:
        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={}
        )

        await self.executor.route_inbound(inbound)

        self.session.add.assert_not_called()

    async def test_route_inbound_creates_message_and_meta(self) -> None:
        recipient = Mock(uuid='wazo-user-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='wazo-user-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.add_message.assert_awaited_once()
        message = self.executor._room_dao.add_message.call_args[0][1]
        assert message.meta is not None
        assert message.meta.backend == 'sms_backend'

    async def test_route_inbound_publishes_message_event(self) -> None:
        recipient = Mock(uuid='wazo-user-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='wazo-user-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.notifier.message_created.assert_awaited_once()

    async def test_route_inbound_resolves_sender_to_wazo_user(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        sender = Mock(uuid='sender-wazo-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid'), Mock(uuid='sender-wazo-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient, '+15559876': sender}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.find_matching_signature = AsyncMock(return_value=None)
        self.executor._room_dao.add_message = AsyncMock()

        await self.executor.route_inbound(inbound)

        call_args = self.executor._room_dao.find_or_create_room.call_args
        participants = call_args.kwargs['participants']
        sender_participant = [
            p for p in participants if str(p.uuid) == 'sender-wazo-uuid'
        ][0]
        assert sender_participant.identity is None

    async def test_route_inbound_unresolved_sender_stays_external(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock()

        await self.executor.route_inbound(inbound)

        call_args = self.executor._room_dao.find_or_create_room.call_args
        participants = call_args.kwargs['participants']
        sender_participant = [p for p in participants if p.identity is not None][0]
        assert sender_participant.identity == '+15559876'

    async def test_route_inbound_echo_dropped(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        sender = Mock(uuid='sender-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid'), Mock(uuid='sender-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient, '+15559876': sender}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        original_meta = Mock(
            status='sent',
            message_uuid='original-msg-uuid',
            message=Mock(room=room),
        )
        self.executor._room_dao.find_matching_signature = AsyncMock(
            return_value=original_meta
        )
        self.executor._room_dao.add_message = AsyncMock()
        self.executor._room_dao.add_delivery_record = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.add_message.assert_not_awaited()
        self.notifier.message_created.assert_not_awaited()
        self.executor._room_dao.add_delivery_record.assert_awaited_once()
        self.notifier.delivery_status_updated.assert_awaited_once()

    async def test_route_inbound_no_echo_creates_message(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        sender = Mock(uuid='sender-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid'), Mock(uuid='sender-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient, '+15559876': sender}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.find_matching_signature = AsyncMock(return_value=None)
        self.executor._room_dao.add_message = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.add_message.assert_awaited_once()

    async def test_route_inbound_returns_retry_delay_on_transient_failure(
        self,
    ) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock(
            side_effect=RuntimeError('DB down')
        )

        delay = await self.executor.route_inbound(inbound, attempt=0)

        assert delay == float(INBOUND_RETRY_DELAYS[0])
        self.notifier.message_created.assert_not_awaited()

    async def test_route_inbound_raises_after_attempts_exhausted(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock(
            side_effect=RuntimeError('DB down')
        )

        with pytest.raises(RuntimeError):
            await self.executor.route_inbound(
                inbound, attempt=len(INBOUND_RETRY_DELAYS)
            )

    async def test_route_inbound_duplicate_external_id_dropped(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.add_message = AsyncMock(
            side_effect=DuplicateExternalIdException(
                inbound.external_id, inbound.backend
            )
        )

        await self.executor.route_inbound(inbound)

        assert self.executor._room_dao.add_message.await_count == 1
        self.notifier.message_created.assert_not_awaited()

    async def test_route_inbound_external_sender_skips_dedup(self) -> None:
        recipient = Mock(uuid='recipient-uuid', tenant_uuid='tenant-uuid')
        room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
        room.users = [Mock(uuid='recipient-uuid')]

        inbound = _make_inbound()

        self.executor._user_identity_dao.resolve_users_by_identities = AsyncMock(
            return_value={'+15551234': recipient}
        )
        self.executor._room_dao.find_or_create_room = AsyncMock(return_value=room)
        self.executor._room_dao.find_matching_signature = AsyncMock()
        self.executor._room_dao.add_message = AsyncMock()

        await self.executor.route_inbound(inbound)

        self.executor._room_dao.find_matching_signature.assert_not_awaited()
        self.executor._room_dao.add_message.assert_awaited_once()


class TestGenerateMessageSignature(unittest.TestCase):
    def test_basic(self) -> None:
        fp = generate_message_signature('+15551234', 'Hello world')
        assert isinstance(fp, str)
        assert len(fp) == 16

    def test_same_input_same_output(self) -> None:
        fp1 = generate_message_signature('+15551234', 'Hello world')
        fp2 = generate_message_signature('+15551234', 'Hello world')
        assert fp1 == fp2

    def test_whitespace_ignored(self) -> None:
        fp1 = generate_message_signature('+15551234', 'Hello world')
        fp2 = generate_message_signature('+15551234', 'Hello  world')
        fp3 = generate_message_signature('+15551234', ' Hello world ')
        assert fp1 == fp2 == fp3

    def test_case_ignored(self) -> None:
        fp1 = generate_message_signature('+15551234', 'Hello World')
        fp2 = generate_message_signature('+15551234', 'hello world')
        assert fp1 == fp2

    def test_non_ascii_stripped(self) -> None:
        fp1 = generate_message_signature('+15551234', 'Hello wörld 🎉')
        fp2 = generate_message_signature('+15551234', 'Hello wörld 🎉')
        assert fp1 == fp2

    def test_different_sender_different_fingerprint(self) -> None:
        fp1 = generate_message_signature('+15551234', 'ok')
        fp2 = generate_message_signature('+15559876', 'ok')
        assert fp1 != fp2

    def test_capped_at_160_chars(self) -> None:
        long_body = 'a' * 300
        fp1 = generate_message_signature('+15551234', long_body)
        fp2 = generate_message_signature('+15551234', 'a' * 160)
        assert fp1 == fp2

    def test_empty_body(self) -> None:
        fp = generate_message_signature('+15551234', '')
        assert isinstance(fp, str)
        assert len(fp) == 16


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

        self.registry = Mock()
        self.store = ConnectorStore(Mock(), ConnectorRegistry())
        self.notifier = AsyncMock()
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=self.registry,
            notifier=self.notifier,
            store=self.store,
        )
        self.executor._room_dao.add_delivery_record = _mock_add_delivery_record()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    def _register_connector(self, status_map: dict) -> None:
        backend_cls = Mock()
        backend_cls.status_map = status_map
        self.registry.get_backend.return_value = backend_cls

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

        record = self.executor._room_dao.add_delivery_record.call_args[0][0]
        assert record.status == 'delivered'

    async def test_ignores_unmapped_status(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})

        await self.executor.route_status_update(_make_status_update(status='queued'))

        self.executor._room_dao.add_delivery_record.assert_not_awaited()

    async def test_drops_when_no_connector(self) -> None:
        self.registry.get_backend.side_effect = KeyError('test')
        await self.executor.route_status_update(_make_status_update())

        self.executor._room_dao.add_delivery_record.assert_not_awaited()

    async def test_drops_when_no_meta(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})
        self.executor._room_dao.get_message_meta_by_external_id = AsyncMock(
            return_value=None
        )

        await self.executor.route_status_update(_make_status_update())

        self.executor._room_dao.add_delivery_record.assert_not_awaited()

    async def test_passes_error_code_as_reason(self) -> None:
        self._register_connector({'failed': DeliveryStatus.FAILED})
        self._mock_meta()

        await self.executor.route_status_update(
            _make_status_update(status='failed', error_code='30003')
        )

        record = self.executor._room_dao.add_delivery_record.call_args[0][0]
        assert record.reason == '30003'

    async def test_publishes_notification(self) -> None:
        self._register_connector({'delivered': DeliveryStatus.DELIVERED})
        self._mock_meta()

        await self.executor.route_status_update(_make_status_update())

        self.notifier.delivery_status_updated.assert_awaited_once()


class TestDeliveryExecutorRecovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.token = _current_session.set(self.session)
        self.executor = DeliveryExecutor(
            config={'uuid': 'test-wazo-uuid'},
            registry=Mock(),
            notifier=AsyncMock(),
            store=ConnectorStore(Mock(), ConnectorRegistry()),
        )

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    def _make_meta(
        self,
        message_uuid: str = 'msg-1',
        retry_count: int = 0,
        extra: dict | None = None,
    ) -> Mock:
        user = Mock(uuid='user-uuid')
        room = Mock(uuid='room-uuid')
        room.users = [user, Mock(uuid='ext-uuid', identity='test:+1555')]
        message = Mock(
            uuid=message_uuid, user_uuid='user-uuid', content='hello', room=room
        )
        meta = Mock()
        meta.message_uuid = message_uuid
        meta.message = message
        meta.retry_count = retry_count
        meta.extra = extra or {}
        return meta

    async def test_no_recoverable_messages(self) -> None:
        self.executor._room_dao.get_recoverable_messages = AsyncMock(return_value=[])

        result = await self.executor.recover_pending_deliveries()

        assert result == []

    async def test_pending_message_recovered_immediately(self) -> None:
        self.executor._room_dao.get_recoverable_messages = AsyncMock(
            return_value=[(self._make_meta(), 'pending')]
        )

        result = await self.executor.recover_pending_deliveries()

        assert len(result) == 1
        message_uuid, delay = result[0]
        assert message_uuid == 'msg-1'
        assert delay == 0.0

    async def test_retrying_message_recovered_with_delay(self) -> None:
        self.executor._room_dao.get_recoverable_messages = AsyncMock(
            return_value=[(self._make_meta(retry_count=1), 'retrying')]
        )

        result = await self.executor.recover_pending_deliveries()

        assert len(result) == 1
        _, delay = result[0]
        assert delay == 30.0

    async def test_pending_recovered(self) -> None:
        meta = self._make_meta()
        self.executor._room_dao.get_recoverable_messages = AsyncMock(
            return_value=[(meta, 'pending')]
        )

        result = await self.executor.recover_pending_deliveries()

        assert len(result) == 1
        message_uuid, delay = result[0]
        assert message_uuid == str(meta.message_uuid)
        assert delay == 0.0

    async def test_skips_meta_with_no_message(self) -> None:
        meta = self._make_meta()
        meta.message = None
        self.executor._room_dao.get_recoverable_messages = AsyncMock(
            return_value=[(meta, 'pending')]
        )

        result = await self.executor.recover_pending_deliveries()

        assert result == []

    async def test_skips_meta_with_no_room(self) -> None:
        meta = self._make_meta()
        meta.message.room = None
        self.executor._room_dao.get_recoverable_messages = AsyncMock(
            return_value=[(meta, 'pending')]
        )

        result = await self.executor.recover_pending_deliveries()

        assert result == []
