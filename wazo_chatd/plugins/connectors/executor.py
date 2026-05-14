# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable
from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageDelivery,
    MessageMeta,
    Room,
    RoomMessage,
    RoomUser,
    User,
)
from wazo_chatd.database.queries.async_ import AsyncDAO
from wazo_chatd.exceptions import DuplicateExternalIdException
from wazo_chatd.plugin_helpers.async_lock import KeyedLock
from wazo_chatd.plugin_helpers.dependencies import ConfigDict
from wazo_chatd.plugin_helpers.tenant import make_uuid5
from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    ConnectorRateLimited,
    ConnectorSendError,
)
from wazo_chatd.plugins.connectors.notifier import AsyncNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
)

logger = logging.getLogger(__name__)

OUTBOUND_RETRY_DELAYS: list[int] = [30, 120, 300]
INBOUND_RETRY_DELAYS: list[int] = [2, 5, 10]
OUTBOUND_MAX_RETRIES: int = len(OUTBOUND_RETRY_DELAYS)
INBOUND_MAX_RETRIES: int = len(INBOUND_RETRY_DELAYS)
ECHO_WINDOW_SECONDS: int = 60
INBOUND_DEDUP_WINDOW_SECONDS: int = 7 * 24 * 3600
MAX_RETRY_AFTER: float = 3600.0

T = TypeVar('T')


def _compute_outbound_retry_delay(retry_count: int) -> float:
    idx = max(0, min(retry_count - 1, len(OUTBOUND_RETRY_DELAYS) - 1))
    return float(OUTBOUND_RETRY_DELAYS[idx])


async def _db_persist_or_delay(
    awaitable: Awaitable[T],
    *,
    attempt: int,
    description: str,
) -> float | None:
    session = get_async_session()

    try:
        await awaitable
    except (SQLAlchemyError, OSError):
        if attempt >= INBOUND_MAX_RETRIES:
            raise

        await session.rollback()
        delay = float(INBOUND_RETRY_DELAYS[attempt])
        logger.warning(
            'Failed to persist %s, retrying in %ds (attempt %d)',
            description,
            delay,
            attempt,
        )
        return delay

    return None


def generate_message_signature(sender_identity: str, body: str) -> str:
    """Generate a dedup signature to detect inbound echoes of outbound messages.

    Combines the sender identity with a normalized body (lowercase, ASCII-only,
    no whitespace, capped at 160 chars) and returns a truncated SHA-256 hash.
    The 160-char cap ensures consistent signatures across providers regardless
    of SMS segment reassembly behavior.
    """
    normalized = ''.join(c.lower() for c in body if c.isascii() and not c.isspace())
    payload = sender_identity + ':' + normalized[:160]

    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class DeliveryExecutor:
    def __init__(
        self,
        config: ConfigDict,
        registry: ConnectorRegistry,
        notifier: AsyncNotifier,
        store: ConnectorStore,
    ) -> None:
        self._wazo_uuid: str = str(config.get('uuid', ''))
        self._registry = registry
        self._notifier = notifier
        self._store = store
        self._dao = AsyncDAO()
        self._room_creation_lock = KeyedLock()

    async def route_outbound_delivery(self, delivery_id: str) -> float | None:
        delivery = await self._dao.room.get_message_delivery(
            delivery_id, skip_locked=True
        )
        if delivery is None:
            logger.debug(
                'Delivery %s unavailable (already in flight or removed), skipping',
                delivery_id,
            )
            return None

        meta = delivery.meta
        if not meta.message or not meta.message.room:
            logger.warning(
                'Delivery %s lost its message or room before dispatch', delivery_id
            )
            return None

        if (sender_record := meta.sender_identity) is None:
            logger.error(
                'Delivery %s has no resolved sender_identity, dead-lettering',
                delivery_id,
            )
            await self._persist_status(
                delivery,
                DeliveryStatus.DEAD_LETTER,
                reason='No sender_identity resolved for message',
            )
            return None
        backend = str(sender_record.backend)
        tenant_uuid = str(sender_record.tenant_uuid)

        try:
            connector = await self._find_connector(backend, tenant_uuid)
        except AuthServiceUnavailableException as exc:
            return await self._record_send_failure(delivery, str(exc))
        except Exception as exc:
            await self._persist_status(
                delivery,
                DeliveryStatus.DEAD_LETTER,
                reason=f'Backend {backend!r} not available: {exc}',
            )
            return None

        message = meta.message
        outbound = OutboundMessage(
            room_uuid=str(message.room.uuid),
            message_uuid=str(message.uuid),
            sender_uuid=str(message.user_uuid),
            body=str(message.content or ''),
            message_type=str(sender_record.type_),
            sender_identity=str(sender_record.identity),
            recipient_identity=str(delivery.recipient_identity),
            metadata={'idempotency_key': str(message.uuid)},
        )

        try:
            external_id = await self._send(connector, outbound)
        except ConnectorRateLimited as exc:
            return await self._record_send_failure(
                delivery, str(exc), retry_after=exc.retry_after
            )
        except ConnectorSendError as exc:
            return await self._record_send_failure(delivery, str(exc))
        except Exception as exc:
            logger.exception(
                'Unexpected error sending message %s via %s',
                meta.message_uuid,
                backend,
            )
            return await self._record_send_failure(delivery, str(exc))

        await self._persist_status(
            delivery, DeliveryStatus.ACCEPTED, external_id=external_id
        )
        return None

    async def route_inbound(
        self, inbound: InboundMessage, *, attempt: int = 0
    ) -> float | None:
        raw_key = inbound.metadata.get('idempotency_key')
        idempotency_key: str | None = str(raw_key) if raw_key else None
        if attempt == 0 and await self._is_duplicate_idempotency(
            idempotency_key, inbound
        ):
            return None

        sender_identity = self._normalize_sender(inbound)

        if (
            resolution := await self._resolve_inbound_room(inbound, sender_identity)
        ) is None:
            return None
        room, sender_participant, sender_user = resolution

        matching_outbound = await self._find_matching_outbound(
            room, sender_user, sender_identity, inbound.body
        )
        if matching_outbound is not None:
            logger.info(
                'Inbound matches recent outbound, treating as delivery confirmation '
                '(room=%s, sender=%s)',
                room.uuid,
                sender_identity,
            )
            await self._confirm_delivery(matching_outbound, inbound.recipient)
            return None

        message = self._build_inbound_message(
            inbound, room, sender_participant, idempotency_key
        )

        try:
            delay = await _db_persist_or_delay(
                self._dao.room.add_message(room, message),
                attempt=attempt,
                description=f'inbound from {inbound.sender}',
            )
        except DuplicateExternalIdException:
            logger.info(
                'Duplicate inbound dropped (backend=%s, external_id=%s)',
                inbound.backend,
                inbound.external_id,
            )
            return None

        if delay is not None:
            return delay

        await self._notifier.message_created(room, message)
        logger.info(
            'Inbound message from %s persisted (room=%s)',
            inbound.sender,
            room.uuid,
        )
        return None

    async def route_status_update(
        self, update: StatusUpdate, *, attempt: int = 0
    ) -> float | None:
        try:
            backend_cls = self._registry.get_backend(update.backend)
        except KeyError:
            logger.warning(
                'No connector for backend %r, dropping status update',
                update.backend,
            )
            return None

        status_map = getattr(backend_cls, 'status_map', {})
        if (mapped_status := status_map.get(update.status)) is None:
            logger.debug(
                'Ignoring unmapped provider status %r for %s',
                update.status,
                update.external_id,
            )
            return None

        meta = await self._dao.room.get_message_meta_by_external_id(
            update.external_id, update.backend
        )
        if not meta:
            logger.warning(
                'No MessageMeta found for external_id %s, dropping status update',
                update.external_id,
            )
            return None

        delivery = next(
            (d for d in meta.deliveries if d.external_id == update.external_id),
            None,
        )
        if delivery is None:
            logger.warning(
                'No MessageDelivery for external_id %s, dropping status update',
                update.external_id,
            )
            return None

        if delivery.status == DeliveryStatus.DELIVERED.value:
            logger.debug(
                'Delivery %s already delivered, ignoring status %s',
                delivery.id,
                update.status,
            )
            return None

        delay = await _db_persist_or_delay(
            self._persist_status(
                delivery, mapped_status, reason=update.error_code or None
            ),
            attempt=attempt,
            description=f'status update for {update.external_id}',
        )
        if delay is not None:
            return delay

        logger.info(
            'Status update: %s → %s (message=%s, external_id=%s)',
            update.status,
            mapped_status.value,
            meta.message_uuid,
            update.external_id,
        )
        return None

    async def recover_pending_deliveries(self) -> list[tuple[str, float]]:
        deliveries = await self._dao.room.get_recoverable_deliveries()
        if not deliveries:
            return []

        recoverable: list[tuple[str, float]] = []
        for delivery, status in deliveries:
            if status == DeliveryStatus.RETRYING.value:
                delay = _compute_outbound_retry_delay(int(delivery.retry_count))
            else:
                delay = 0.0
            recoverable.append((str(delivery.id), delay))

        logger.info('Recovery: %d delivery(ies) to re-enqueue', len(recoverable))
        return recoverable

    async def get_message_meta(self, message_uuid: str) -> MessageMeta | None:
        return await self._dao.room.get_message_meta(message_uuid)

    async def list_pending_external_ids(
        self, tenant_uuid: str, backend: str
    ) -> list[str]:
        return await self._dao.room.list_pending_external_ids(tenant_uuid, backend)

    async def _record_send_failure(
        self,
        delivery: MessageDelivery,
        reason: str,
        *,
        retry_after: float | None = None,
    ) -> float | None:
        delivery.retry_count = int(delivery.retry_count) + 1  # type: ignore[assignment]

        if int(delivery.retry_count) > OUTBOUND_MAX_RETRIES:
            await self._persist_status(
                delivery,
                DeliveryStatus.DEAD_LETTER,
                reason=f'Max retries exceeded ({reason})',
            )
            return None

        await self._persist_status(delivery, DeliveryStatus.RETRYING, reason=reason)

        if retry_after is not None:
            return min(retry_after, MAX_RETRY_AFTER)

        return _compute_outbound_retry_delay(int(delivery.retry_count))

    async def _is_duplicate_idempotency(
        self,
        idempotency_key: str | None,
        inbound: InboundMessage,
    ) -> bool:
        if idempotency_key is None:
            return False

        if is_duplicate := await self._dao.room.check_duplicate_idempotency_key(
            idempotency_key,
            recipient=inbound.recipient,
            backend=inbound.backend,
            message_type=inbound.message_type,
            window_seconds=INBOUND_DEDUP_WINDOW_SECONDS,
        ):
            logger.info('Duplicate inbound message skipped (key=%s)', idempotency_key)

        return is_duplicate

    def _normalize_sender(self, inbound: InboundMessage) -> str:
        try:
            backend_cls = self._registry.get_backend(inbound.backend)
            return backend_cls.normalize_identity(inbound.sender)
        except (KeyError, ValueError, TypeError):
            return inbound.sender

    async def _resolve_inbound_room(
        self, inbound: InboundMessage, sender_identity: str
    ) -> tuple[Room, RoomUser, User | None] | None:
        resolved = await self._dao.user_identity.resolve_users_by_identities(
            [inbound.recipient, sender_identity]
        )

        if not (recipient_user := resolved.get(inbound.recipient)):
            logger.warning(
                'No wazo user found for recipient %s (backend=%s), dropping',
                inbound.recipient,
                inbound.backend,
            )
            return None

        tenant_uuid = str(recipient_user.tenant_uuid)

        sender_user = resolved.get(sender_identity)
        sender_participant = RoomUser(
            uuid=(
                sender_user.uuid
                if sender_user
                else make_uuid5(tenant_uuid, sender_identity)
            ),
            tenant_uuid=tenant_uuid,
            wazo_uuid=self._wazo_uuid,
            identity=None if sender_user else sender_identity,
        )

        recipient_participant = RoomUser(
            uuid=recipient_user.uuid,
            tenant_uuid=tenant_uuid,
            wazo_uuid=self._wazo_uuid,
        )

        participants = [sender_participant, recipient_participant]
        room = await self._get_or_create_room(tenant_uuid, participants)

        return room, sender_participant, sender_user

    async def _get_or_create_room(
        self, tenant_uuid: str, participants: list[RoomUser]
    ) -> Room:
        lock_key = (tenant_uuid, tuple(sorted(str(p.uuid) for p in participants)))
        async with self._room_creation_lock.acquire(lock_key):
            existing = await self._dao.room.find_room(tenant_uuid, participants)
            if existing is not None:
                return existing
            room = await self._dao.room.create_room(tenant_uuid, participants)
        await self._notifier.room_created(room)
        return room

    async def _find_matching_outbound(
        self,
        room: Room,
        sender_user: User | None,
        sender_identity: str,
        body: str,
    ) -> MessageMeta | None:
        if not sender_user or not body:
            return None

        signature = generate_message_signature(sender_identity, body)
        return await self._dao.room.find_matching_signature(
            str(room.uuid), signature, ECHO_WINDOW_SECONDS
        )

    def _build_inbound_message(
        self,
        inbound: InboundMessage,
        room: Room,
        sender_participant: RoomUser,
        idempotency_key: str | None,
    ) -> RoomMessage:
        extra: dict[str, str] = {}
        if idempotency_key is not None:
            extra['inbound_idempotency_key'] = idempotency_key

        delivery = MessageDelivery(
            recipient_identity=inbound.recipient,
            backend=inbound.backend,
            type_=inbound.message_type,
            external_id=inbound.external_id,
        )
        delivery.records.append(DeliveryRecord(status=DeliveryStatus.DELIVERED.value))
        meta = MessageMeta(
            extra=extra,
            deliveries=[delivery],
        )
        return RoomMessage(
            room_uuid=room.uuid,
            content=inbound.body,
            user_uuid=sender_participant.uuid,
            tenant_uuid=str(sender_participant.tenant_uuid),
            wazo_uuid=self._wazo_uuid,
            meta=meta,
        )

    async def _confirm_delivery(
        self, meta: MessageMeta, recipient_identity: str
    ) -> None:
        delivery = next(
            (d for d in meta.deliveries if d.recipient_identity == recipient_identity),
            None,
        )
        if delivery is None:
            logger.warning(
                'No MessageDelivery for recipient %s on meta %s, cannot confirm',
                recipient_identity,
                meta.message_uuid,
            )
            return

        if delivery.status == DeliveryStatus.DELIVERED.value:
            return

        await self._persist_status(delivery, DeliveryStatus.DELIVERED)
        logger.info(
            'Confirmed delivery for message %s recipient %s',
            meta.message_uuid,
            recipient_identity,
        )

    async def _persist_status(
        self,
        delivery: MessageDelivery,
        status: DeliveryStatus,
        *,
        reason: str | None = None,
        external_id: str | None = None,
    ) -> DeliveryRecord:
        if external_id is not None:
            delivery.external_id = external_id  # type: ignore[assignment]

        record = await self._dao.room.add_delivery_record(
            delivery, status, reason=reason
        )
        delivery.records.append(record)
        await self._notifier.delivery_status_updated(delivery, record)
        return record

    async def _find_connector(self, backend: str, tenant_uuid: str) -> Connector:
        if connector := self._store.peek(backend, tenant_uuid):
            return connector

        return await asyncio.to_thread(self._store.get, backend, tenant_uuid)

    async def _send(
        self,
        connector: Connector,
        outbound: OutboundMessage,
    ) -> str:
        if asyncio.iscoroutinefunction(connector.send):
            return await connector.send(outbound)  # type: ignore[misc]
        return await asyncio.to_thread(connector.send, outbound)
