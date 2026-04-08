# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Delivery executor — runs in the server (worker) process.

Uses asyncio for I/O-bound operations (DB writes, external API calls).
Sync connector implementations are wrapped with ``asyncio.to_thread()``.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from typing import Any

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageMeta,
    Room,
    RoomMessage,
    RoomUser,
)
from wazo_chatd.database.queries.async_.room import AsyncRoomDAO
from wazo_chatd.database.queries.async_.user_identity import AsyncUserIdentityDAO
from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.exceptions import ConnectorSendError
from wazo_chatd.plugins.connectors.notifier import AsyncNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
)

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3
RETRY_DELAYS: list[int] = [30, 120, 300]


class DeliveryExecutor:
    """Executes connector send operations with delivery tracking and retries.

    Connectors are initialized locally from configuration received via
    pipe from the main process.  The executor never queries the DB for
    provider configuration — it only writes delivery status records.
    """

    def __init__(
        self,
        config: dict[str, Any],
        registry: ConnectorRegistry,
        notifier: AsyncNotifier,
        store: ConnectorStore,
    ) -> None:
        self._wazo_uuid: str = str(config.get('uuid', ''))
        self._connector_config: dict[str, Any] = dict(config.get('connectors', {}))
        self._registry = registry
        self._notifier = notifier
        self._store = store
        self._room_dao = AsyncRoomDAO()
        self._user_identity_dao = AsyncUserIdentityDAO()

    async def route_outbound(self, meta: MessageMeta) -> None:
        assert (sender_record := meta.sender_identity)

        session = get_async_session()
        message = meta.message
        room = message.room

        sender_identity = str(sender_record.identity)
        backend_name = str(sender_record.backend)
        message_type = str(sender_record.type_)

        recipient_identity = await self._resolve_recipient_identity(
            room, message, backend_name
        )
        if not recipient_identity:
            return

        meta.extra = {
            **(meta.extra or {}),
            'outbound_idempotency_key': str(meta.message_uuid),
        }
        await session.flush()

        outbound = OutboundMessage(
            room_uuid=str(room.uuid),
            message_uuid=str(meta.message_uuid),
            sender_uuid=str(message.user_uuid),
            body=str(message.content or ''),
            message_type=message_type,
            sender_identity=sender_identity,
            recipient_identity=recipient_identity,
            metadata={'idempotency_key': str(meta.message_uuid)},
        )

        await self.execute(
            outbound,
            meta,
            tenant_uuid=str(sender_record.tenant_uuid),
            room_uuid=str(room.uuid),
            user_uuids=[str(u.uuid) for u in room.users],
        )

    async def _resolve_recipient_identity(
        self,
        room: Room,
        message: RoomMessage,
        backend: str,
    ) -> str | None:
        recipients = [u for u in room.users if u.uuid != message.user_uuid]
        if not recipients:
            return None

        recipient = recipients[0]

        if recipient.identity:
            return str(recipient.identity)

        identities = await self._user_identity_dao.list_by_user(
            str(recipient.uuid), backends=[backend]
        )
        if not identities:
            logger.warning(
                'No %s identity for recipient %s, skipping',
                backend,
                recipient.uuid,
            )
            return None

        return str(identities[0].identity)

    async def route_inbound(
        self,
        inbound: InboundMessage,
    ) -> None:
        idempotency_key = inbound.metadata.get('idempotency_key')
        if idempotency_key:
            is_duplicate = await self._room_dao.check_duplicate_idempotency_key(
                str(idempotency_key)
            )
            if is_duplicate:
                logger.info(
                    'Duplicate inbound message skipped (key=%s)',
                    idempotency_key,
                )
                return

        sender_identity = inbound.sender
        try:
            backend_cls = self._registry.get_backend(inbound.backend)
            sender_identity = backend_cls.normalize_identity(sender_identity)
        except (KeyError, ValueError, TypeError):
            pass

        resolved = await self._user_identity_dao.resolve_users_by_identities(
            [inbound.recipient, sender_identity]
        )

        recipient_user = resolved.get(inbound.recipient)
        if not recipient_user:
            logger.warning(
                'No wazo user found for recipient %s (backend=%s), dropping',
                inbound.recipient,
                inbound.backend,
            )
            return

        tenant_uuid = str(recipient_user.tenant_uuid)
        wazo_uuid = self._wazo_uuid

        recipient_participant = RoomUser(
            uuid=recipient_user.uuid,
            tenant_uuid=tenant_uuid,
            wazo_uuid=wazo_uuid,
        )

        sender_user = resolved.get(sender_identity)
        if sender_user:
            sender_participant = RoomUser(
                uuid=sender_user.uuid,
                tenant_uuid=tenant_uuid,
                wazo_uuid=wazo_uuid,
            )
        else:
            sender_participant = RoomUser(
                uuid=uuid.uuid5(uuid.NAMESPACE_URL, f'{tenant_uuid}:{sender_identity}'),
                tenant_uuid=tenant_uuid,
                wazo_uuid=wazo_uuid,
                identity=sender_identity,
            )
        room = await self._room_dao.find_or_create_room(
            tenant_uuid=tenant_uuid,
            participants=[sender_participant, recipient_participant],
        )

        extra: dict[str, str] = {'external_id': inbound.external_id}
        if idempotency_key:
            extra['idempotency_key'] = str(idempotency_key)

        record = DeliveryRecord(status=DeliveryStatus.DELIVERED.value)
        meta = MessageMeta(
            backend=inbound.backend,
            type_=inbound.message_type,
            extra=extra,
            records=[record],
        )
        message = RoomMessage(
            room_uuid=room.uuid,
            content=inbound.body,
            user_uuid=sender_participant.uuid,
            tenant_uuid=tenant_uuid,
            wazo_uuid=wazo_uuid,
            meta=meta,
        )
        await self._room_dao.add_message(room, message)

        await self._notifier.message_created(room, message)
        logger.info(
            'Inbound message from %s persisted (room=%s)',
            inbound.sender,
            room.uuid,
        )

    async def route_status_update(self, update: StatusUpdate) -> None:
        try:
            backend_cls = self._registry.get_backend(update.backend)
        except KeyError:
            logger.warning(
                'No connector for backend %r, dropping status update',
                update.backend,
            )
            return

        status_map = getattr(backend_cls, 'status_map', {})
        mapped_status = status_map.get(update.status)
        if not mapped_status:
            logger.debug(
                'Ignoring unmapped provider status %r for %s',
                update.status,
                update.external_id,
            )
            return

        meta = await self._room_dao.get_message_meta_by_external_id(update.external_id)
        if not meta:
            logger.warning(
                'No MessageMeta found for external_id %s, dropping status update',
                update.external_id,
            )
            return

        record = DeliveryRecord(
            status=mapped_status.value,
            reason=update.error_code or None,
        )
        await self._room_dao.add_delivery_record(meta, record)

        room = meta.message.room
        await self._notifier.delivery_status_updated(
            message_uuid=str(meta.message_uuid),
            status=mapped_status.value,
            timestamp=record.timestamp.isoformat(),
            backend=update.backend,
            tenant_uuid=str(room.tenant_uuid),
            room_uuid=str(room.uuid),
            user_uuids=[str(u.uuid) for u in room.users],
        )

        logger.info(
            'Status update: %s → %s (external_id=%s)',
            update.status,
            mapped_status.value,
            update.external_id,
        )

    async def recover_pending_deliveries(
        self,
    ) -> list[tuple[MessageMeta, float]]:
        metas = await self._room_dao.get_recoverable_messages()
        if not metas:
            return []

        recoverable: list[tuple[MessageMeta, float]] = []
        for meta, status in metas:
            if not meta.message or not meta.message.room:
                logger.warning(
                    'Recovery: meta %s has no message or room, skipping',
                    meta.message_uuid,
                )
                continue

            if status == DeliveryStatus.RETRYING.value:
                retry_idx = min(int(meta.retry_count or 0), len(RETRY_DELAYS) - 1)
                delay = float(RETRY_DELAYS[retry_idx])
            else:
                delay = 0.0

            recoverable.append((meta, delay))

        logger.info('Recovery: %d message(s) to re-enqueue', len(recoverable))
        return recoverable

    async def execute(
        self,
        outbound: OutboundMessage,
        delivery: MessageMeta,
        tenant_uuid: str = '',
        room_uuid: str = '',
        user_uuids: list[str] | None = None,
    ) -> None:
        backend = str(delivery.backend)
        last_status = DeliveryStatus.PENDING
        connector = await self._find_connector(backend, tenant_uuid)
        if connector is None:
            last_status = DeliveryStatus.DEAD_LETTER
            last_record = await self._add_record(
                delivery,
                last_status,
                reason=f'Backend {backend!r} not available',
            )
        else:
            await self._add_record(delivery, DeliveryStatus.SENDING)

            try:
                external_id = await self._send(connector, outbound)
                delivery.external_id = external_id  # type: ignore[assignment]
                last_status = DeliveryStatus.SENT
                last_record = await self._add_record(delivery, last_status)

            except ConnectorSendError as exc:
                delivery.retry_count += 1  # type: ignore[assignment]
                last_status = DeliveryStatus.FAILED
                await self._add_record(
                    delivery,
                    last_status,
                    reason=str(exc),
                )

                if delivery.retry_count >= MAX_RETRIES:  # type: ignore[operator]
                    last_status = DeliveryStatus.DEAD_LETTER
                    last_record = await self._add_record(
                        delivery,
                        last_status,
                        reason=f'Max retries ({MAX_RETRIES}) exceeded',
                    )
                else:
                    last_status = DeliveryStatus.RETRYING
                    last_record = await self._add_record(delivery, last_status)

        await self._notifier.delivery_status_updated(
            message_uuid=str(delivery.message_uuid),
            status=last_status.value,
            timestamp=last_record.timestamp.isoformat(),
            backend=backend,
            tenant_uuid=tenant_uuid,
            room_uuid=room_uuid,
            user_uuids=user_uuids or [],
        )

    async def _find_connector(self, backend: str, tenant_uuid: str) -> Connector | None:
        """Find a connector instance, refreshing the cache if needed."""
        connector = self._store.find_by_backend(backend, tenant_uuid)
        if connector:
            return connector

        return await self._store.refresh(backend, tenant_uuid)

    async def _send(
        self,
        connector: Connector,
        outbound: OutboundMessage,
    ) -> str:
        """Call connector.send(), wrapping sync implementations."""
        if inspect.iscoroutinefunction(connector.send):
            return await connector.send(outbound)  # type: ignore[misc]
        return await asyncio.to_thread(connector.send, outbound)

    async def _add_record(
        self,
        delivery: MessageMeta,
        status: DeliveryStatus,
        reason: str | None = None,
    ) -> DeliveryRecord:
        record = DeliveryRecord(
            status=status.value,
            reason=reason,
        )
        await self._room_dao.add_delivery_record(delivery, record)
        return record
