# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, ClassVar
from unittest.mock import AsyncMock, Mock

from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import DeliveryRecord
from wazo_chatd.plugin_helpers.dependencies import ConfigDict
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
    TransportData,
)

FIXED_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_config() -> ConfigDict:
    return {
        'db_uri': 'postgresql://localhost/test',
        'uuid': 'svc-uuid',
        'bus': {},
        'delivery': {'max_concurrent_tasks': 100},
    }


def make_inbound(idempotency_key: str | None = None) -> InboundMessage:
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


def make_outbound(message_uuid: str = 'delivery-1') -> OutboundMessage:
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


def make_status_update(
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


def make_recipient_room(*user_uuids: str) -> tuple[Mock, Mock]:
    recipient = Mock(uuid=user_uuids[0], tenant_uuid='tenant-uuid')
    room = Mock(uuid='room-uuid', tenant_uuid='tenant-uuid')
    room.users = [Mock(uuid=u) for u in user_uuids]
    return recipient, room


def make_room_user(uuid: str = 'user-uuid', identity: str | None = None) -> Mock:
    user = Mock()
    user.uuid = uuid
    user.identity = identity
    return user


def make_room(
    users: list[Mock] | None = None,
    *,
    uuid: str = 'room-uuid',
    tenant_uuid: str = 'tenant-uuid',
) -> Mock:
    room = Mock()
    room.uuid = uuid
    room.tenant_uuid = tenant_uuid
    room.users = users or []
    return room


def mock_asyncpg_conn() -> AsyncMock:
    conn = AsyncMock()
    conn.is_closed = Mock(return_value=True)
    return conn


def mock_session_factory() -> Mock:
    result_mock = Mock()
    result_mock.all.return_value = []
    result_mock.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute.return_value = result_mock
    return Mock(return_value=session)


def mock_store() -> Mock:
    store = Mock()
    store.items.return_value = []
    store.wait_populated = AsyncMock()
    return store


def mock_instance(backend: str) -> Mock:
    instance = Mock()
    instance.backend = backend
    return instance


def mock_add_delivery_record() -> AsyncMock:
    async def _side_effect(delivery, status, reason=None):
        return DeliveryRecord(
            delivery_id=delivery.id,
            status=status.value,
            reason=reason,
            timestamp=FIXED_NOW,
        )

    return AsyncMock(side_effect=_side_effect)


def build_registry(*backends: type) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    for cls in backends:
        registry.register_backend(cls)  # type: ignore[arg-type]
    return registry


class FakeConnector:
    backend: ClassVar[str] = 'sms_backend'
    supported_types: ClassVar[tuple[str, ...]] = ('sms',)
    status_map: ClassVar[dict[str, DeliveryStatus]] = {}

    def __init__(
        self,
        tenant_uuid: str | None = None,
        provider_config: Mapping[str, Any] | None = None,
        connector_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.tenant_uuid = tenant_uuid
        self.provider_config = provider_config
        self.connector_config = connector_config
        self.send_return = 'ext-msg-id-123'
        self.send_side_effect: Exception | None = None
        self.last_sent: OutboundMessage | None = None

    def send(self, message: OutboundMessage) -> str:
        self.last_sent = message
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
