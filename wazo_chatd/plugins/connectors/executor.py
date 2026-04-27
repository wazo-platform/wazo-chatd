# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Delivery executor — runs in the server (worker) process.

Uses asyncio for I/O-bound operations (DB writes, external API calls).
Sync connector implementations are wrapped with ``asyncio.to_thread()``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageMeta,
    Room,
    RoomMessage,
    RoomUser,
    User,
    UserIdentity,
)
from wazo_chatd.database.queries.async_.room import AsyncRoomDAO
from wazo_chatd.database.queries.async_.user_identity import AsyncUserIdentityDAO
from wazo_chatd.exceptions import DuplicateExternalIdException
from wazo_chatd.plugin_helpers.dependencies import ConfigDict
from wazo_chatd.plugin_helpers.tenant import make_uuid5
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

OUTBOUND_MAX_RETRIES: int = 3
OUTBOUND_RETRY_DELAYS: list[int] = [30, 120, 300]
INBOUND_MAX_RETRIES: int = 3
INBOUND_RETRY_DELAYS: list[int] = [2, 5, 10]
ECHO_WINDOW_SECONDS: int = 60


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
    """Executes connector send operations with delivery tracking and retries.

    Connectors are initialized locally from configuration received via
    pipe from the main process.  The executor never queries the DB for
    provider configuration — it only writes delivery status records.
    """

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
        self._room_dao = AsyncRoomDAO()
        self._user_identity_dao = AsyncUserIdentityDAO()

    async def route_outbound(self, meta: MessageMeta) -> float | None:
        """Resolve recipient, send, and record outcome. Returns retry delay if RETRYING."""
        assert (sender_record := meta.sender_identity)
        backend = str(sender_record.backend)
        tenant_uuid = str(sender_record.tenant_uuid)

        recipient_identity = await self._resolve_recipient_identity(
            meta.message.room, meta.message, backend
        )
        if not recipient_identity:
            return None

        await self._persist_outbound_extras(meta, str(sender_record.identity))
        outbound = self._build_outbound(meta, sender_record, recipient_identity)

        connector = await self._find_connector(backend, tenant_uuid)
        if connector is None:
            await self._persist_status(
                meta,
                DeliveryStatus.DEAD_LETTER,
                reason=f'Backend {backend!r} not available',
            )
            return None

        try:
            external_id = await self._send(connector, outbound)
        except ConnectorSendError as exc:
            return await self._record_send_failure(meta, str(exc))
        except Exception as exc:
            logger.exception(
                'Unexpected error sending message %s via %s',
                meta.message_uuid,
                backend,
            )
            return await self._record_send_failure(meta, str(exc))

        await self._persist_status(
            meta, DeliveryStatus.ACCEPTED, external_id=external_id
        )
        return None

    async def route_inbound(
        self, inbound: InboundMessage, *, attempt: int = 0
    ) -> float | None:
        idempotency_key = inbound.metadata.get('idempotency_key')
        if attempt == 0 and await self._is_duplicate_idempotency(idempotency_key):
            return None

        sender_identity = self._normalize_sender(inbound)
        resolution = await self._resolve_participants(inbound, sender_identity)
        if resolution is None:
            return None
        room, sender_participant, sender_user = resolution

        if await self._is_outbound_echo(
            room, sender_user, sender_identity, inbound.body
        ):
            return None

        message = self._build_inbound_message(
            inbound, room, sender_participant, idempotency_key
        )

        session = get_async_session()
        try:
            await self._room_dao.add_message(room, message)
        except DuplicateExternalIdException:
            logger.info(
                'Duplicate inbound dropped (backend=%s, external_id=%s)',
                inbound.backend,
                inbound.external_id,
            )
            return None
        except Exception:
            if attempt >= len(INBOUND_RETRY_DELAYS):
                raise
            await session.rollback()
            delay = float(INBOUND_RETRY_DELAYS[attempt])
            logger.warning(
                'Failed to persist inbound from %s, retrying in %ds (attempt %d)',
                inbound.sender,
                delay,
                attempt,
            )
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
        mapped_status = status_map.get(update.status)
        if not mapped_status:
            logger.debug(
                'Ignoring unmapped provider status %r for %s',
                update.status,
                update.external_id,
            )
            return None

        meta = await self._room_dao.get_message_meta_by_external_id(update.external_id)
        if not meta:
            logger.warning(
                'No MessageMeta found for external_id %s, dropping status update',
                update.external_id,
            )
            return None

        if meta.status == DeliveryStatus.DELIVERED.value:
            logger.debug(
                'Message %s already delivered, ignoring status %s',
                meta.message_uuid,
                update.status,
            )
            return None

        record = DeliveryRecord(
            message_uuid=meta.message_uuid,
            status=mapped_status.value,
            reason=update.error_code or None,
        )
        session = get_async_session()
        try:
            await self._room_dao.add_delivery_record(record)
        except Exception:
            if attempt >= len(INBOUND_RETRY_DELAYS):
                raise
            await session.rollback()
            delay = float(INBOUND_RETRY_DELAYS[attempt])
            logger.warning(
                'Failed to persist status update for %s, retrying in %ds (attempt %d)',
                update.external_id,
                delay,
                attempt,
            )
            return delay

        room = meta.message.room
        await self._notifier.delivery_status_updated(meta, record, room)

        logger.info(
            'Status update: %s → %s (message=%s, external_id=%s)',
            update.status,
            mapped_status.value,
            meta.message_uuid,
            update.external_id,
        )
        return None

    async def recover_pending_deliveries(self) -> list[tuple[str, float]]:
        metas = await self._room_dao.get_recoverable_messages()
        if not metas:
            return []

        recoverable: list[tuple[str, float]] = []
        for meta, status in metas:
            if not meta.message or not meta.message.room:
                logger.warning(
                    'Recovery: meta %s has no message or room, skipping',
                    meta.message_uuid,
                )
                continue

            if status == DeliveryStatus.RETRYING.value:
                retry_idx = min(
                    max(int(meta.retry_count or 0) - 1, 0),
                    len(OUTBOUND_RETRY_DELAYS) - 1,
                )
                delay = float(OUTBOUND_RETRY_DELAYS[retry_idx])
            else:
                delay = 0.0

            recoverable.append((str(meta.message_uuid), delay))

        logger.info('Recovery: %d message(s) to re-enqueue', len(recoverable))
        return recoverable

    async def get_message_meta(self, message_uuid: str) -> MessageMeta | None:
        return await self._room_dao.get_message_meta(message_uuid)

    async def list_pending_external_ids(
        self, tenant_uuid: str, backend: str
    ) -> list[str]:
        return await self._room_dao.list_pending_external_ids(tenant_uuid, backend)

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

    async def _persist_outbound_extras(
        self, meta: MessageMeta, sender_identity: str
    ) -> None:
        message = meta.message
        has_internal_recipient = any(
            u.uuid != message.user_uuid and not u.identity for u in message.room.users
        )
        extra = {
            **(meta.extra or {}),
            'outbound_idempotency_key': str(meta.message_uuid),
        }
        if has_internal_recipient:
            extra['message_signature'] = generate_message_signature(
                sender_identity, str(message.content or '')
            )
        meta.extra = extra  # type: ignore[assignment]
        session = get_async_session()
        await session.flush()

    @staticmethod
    def _build_outbound(
        meta: MessageMeta,
        sender_record: UserIdentity,
        recipient_identity: str,
    ) -> OutboundMessage:
        message = meta.message
        return OutboundMessage(
            room_uuid=str(message.room.uuid),
            message_uuid=str(meta.message_uuid),
            sender_uuid=str(message.user_uuid),
            body=str(message.content or ''),
            message_type=str(sender_record.type_),
            sender_identity=str(sender_record.identity),
            recipient_identity=recipient_identity,
            metadata={'idempotency_key': str(meta.message_uuid)},
        )

    async def _record_send_failure(
        self, meta: MessageMeta, reason: str
    ) -> float | None:
        meta.retry_count = int(meta.retry_count or 0) + 1  # type: ignore[assignment]
        if meta.retry_count >= OUTBOUND_MAX_RETRIES:  # type: ignore[operator]
            await self._persist_status(
                meta,
                DeliveryStatus.DEAD_LETTER,
                reason=f'Max retries exceeded ({reason})',
            )
            return None
        await self._persist_status(meta, DeliveryStatus.RETRYING, reason=reason)
        idx = min(int(meta.retry_count) - 1, len(OUTBOUND_RETRY_DELAYS) - 1)  # type: ignore[arg-type]
        return float(OUTBOUND_RETRY_DELAYS[idx])

    async def _is_duplicate_idempotency(self, idempotency_key: str | None) -> bool:
        if not idempotency_key:
            return False
        is_duplicate = await self._room_dao.check_duplicate_idempotency_key(
            str(idempotency_key)
        )
        if is_duplicate:
            logger.info('Duplicate inbound message skipped (key=%s)', idempotency_key)
        return is_duplicate

    def _normalize_sender(self, inbound: InboundMessage) -> str:
        try:
            backend_cls = self._registry.get_backend(inbound.backend)
            return backend_cls.normalize_identity(inbound.sender)
        except (KeyError, ValueError, TypeError):
            return inbound.sender

    async def _resolve_participants(
        self, inbound: InboundMessage, sender_identity: str
    ) -> tuple[Room, RoomUser, User | None] | None:
        resolved = await self._user_identity_dao.resolve_users_by_identities(
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

        room = await self._room_dao.find_or_create_room(
            tenant_uuid=tenant_uuid,
            participants=[sender_participant, recipient_participant],
        )

        return room, sender_participant, sender_user

    async def _is_outbound_echo(
        self,
        room: Room,
        sender_user: User | None,
        sender_identity: str,
        body: str,
    ) -> bool:
        if not sender_user or not body:
            return False

        signature = generate_message_signature(sender_identity, body)
        original_meta = await self._room_dao.find_matching_signature(
            str(room.uuid), signature, ECHO_WINDOW_SECONDS
        )

        if not original_meta:
            return False

        logger.info(
            'Duplicate inbound message dropped (room=%s, sender=%s)',
            room.uuid,
            sender_identity,
        )
        await self._confirm_delivery(original_meta)
        return True

    def _build_inbound_message(
        self,
        inbound: InboundMessage,
        room: Room,
        sender_participant: RoomUser,
        idempotency_key: object | None,
    ) -> RoomMessage:
        extra: dict[str, str] = {}
        if idempotency_key:
            extra['idempotency_key'] = str(idempotency_key)

        record = DeliveryRecord(status=DeliveryStatus.DELIVERED.value)
        meta = MessageMeta(
            backend=inbound.backend,
            type_=inbound.message_type,
            external_id=inbound.external_id,
            extra=extra,
            records=[record],
        )
        return RoomMessage(
            room_uuid=room.uuid,
            content=inbound.body,
            user_uuid=sender_participant.uuid,
            tenant_uuid=str(sender_participant.tenant_uuid),
            wazo_uuid=self._wazo_uuid,
            meta=meta,
        )

    async def _confirm_delivery(self, meta: MessageMeta) -> None:
        if meta.status == DeliveryStatus.DELIVERED.value:
            return

        record = DeliveryRecord(
            message_uuid=meta.message_uuid,
            status=DeliveryStatus.DELIVERED.value,
        )
        await self._room_dao.add_delivery_record(record)

        room = meta.message.room
        await self._notifier.delivery_status_updated(meta, record, room)

        logger.info('Confirmed delivery for message %s', meta.message_uuid)

    async def _persist_status(
        self,
        delivery: MessageMeta,
        status: DeliveryStatus,
        *,
        reason: str | None = None,
        external_id: str | None = None,
    ) -> DeliveryRecord:
        if external_id is not None:
            delivery.external_id = external_id  # type: ignore[assignment]
        record = await self._add_record(delivery, status, reason=reason)
        await self._notifier.delivery_status_updated(
            delivery, record, delivery.message.room
        )
        return record

    async def _find_connector(self, backend: str, tenant_uuid: str) -> Connector | None:
        """Find a connector instance, refreshing the cache if needed."""
        connector = self._store.peek(backend, tenant_uuid)
        if connector:
            return connector

        return await self._store.refresh(backend, tenant_uuid)

    async def _send(
        self,
        connector: Connector,
        outbound: OutboundMessage,
    ) -> str:
        """Call connector.send(), wrapping sync implementations."""
        if asyncio.iscoroutinefunction(connector.send):
            return await connector.send(outbound)  # type: ignore[misc]
        return await asyncio.to_thread(connector.send, outbound)

    async def _add_record(
        self,
        delivery: MessageMeta,
        status: DeliveryStatus,
        reason: str | None = None,
    ) -> DeliveryRecord:
        record = DeliveryRecord(
            message_uuid=delivery.message_uuid,
            status=status.value,
            reason=reason,
        )
        await self._room_dao.add_delivery_record(record)
        return record
