# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Delivery executor — runs in the server (worker) process.

Uses asyncio for I/O-bound operations (DB writes, external API calls).
Sync connector implementations are wrapped with ``asyncio.to_thread()``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from wazo_chatd.connectors.connector import Connector
from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.connectors.delivery import MAX_RETRIES, DeliveryStatus
from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.notifier import AsyncNotifier
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.store import ConnectorStore
from wazo_chatd.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
    RoomParticipant,
)
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageMeta,
    RoomMessage,
    RoomUser,
)
from wazo_chatd.database.queries.async_.room import AsyncRoomDAO
from wazo_chatd.database.queries.async_.user_alias import AsyncUserAliasDAO


logger = logging.getLogger(__name__)


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
        self._user_alias_dao = AsyncUserAliasDAO()

    async def route_outbound(
        self,
        outbound: OutboundMessage,
    ) -> None:
        external = [p for p in outbound.participants if p.identity]
        if not external:
            return

        capabilities = self._resolve_capabilities(external)
        if not capabilities:
            logger.warning(
                'No common connector type for message %s',
                outbound.message_uuid,
            )
            return

        chosen_type = next(iter(capabilities))
        recipient_identity = str(external[0].identity)

        aliases = await self._user_alias_dao.list_by_user_and_types(
            outbound.sender_uuid, [chosen_type]
        )
        sender_alias = str(aliases[0].identity) if aliases else ''
        backend_name = (
            str(aliases[0].provider.backend)
            if aliases and aliases[0].provider
            else chosen_type
        )

        # TODO: review — retry handles race between sync commit and
        # async pickup. The meta is created by the sync side in the
        # same transaction as the RoomMessage.
        meta = None
        for attempt in range(5):
            meta = await self._room_dao.get_message_meta(
                outbound.message_uuid
            )
            if meta:
                break
            await asyncio.sleep(0.2)

        if not meta:
            logger.error(
                'No MessageMeta found for message %s after retries, skipping',
                outbound.message_uuid,
            )
            return

        meta.type_ = chosen_type  # type: ignore[assignment]
        meta.backend = backend_name  # type: ignore[assignment]
        meta.extra = {'outbound_idempotency_key': outbound.message_uuid}  # type: ignore[assignment]
        await get_async_session().flush()

        resolved = OutboundMessage(
            room_uuid=outbound.room_uuid,
            message_uuid=outbound.message_uuid,
            sender_uuid=outbound.sender_uuid,
            body=outbound.body,
            sender_alias=sender_alias,
            recipient_alias=recipient_identity,
            metadata=outbound.metadata,
        )
        tenant_uuid = str(aliases[0].tenant_uuid) if aliases else ''
        user_uuids = [p.uuid for p in outbound.participants]
        await self.execute(
            resolved, meta,
            tenant_uuid=tenant_uuid,
            room_uuid=outbound.room_uuid,
            user_uuids=user_uuids,
        )

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

        recipient_alias = await self._user_alias_dao.find_by_identity_and_backend(
            inbound.recipient, inbound.backend
        )
        if not recipient_alias:
            logger.warning(
                'No user alias found for recipient %s (backend=%s), dropping',
                inbound.recipient,
                inbound.backend,
            )
            return

        tenant_uuid = str(recipient_alias.tenant_uuid)
        user = recipient_alias.user
        user_uuid = str(user.uuid)
        wazo_uuid = self._wazo_uuid
        sender_uuid = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f'{tenant_uuid}:{inbound.sender}')
        )

        sender_participant = RoomUser(
            uuid=sender_uuid,
            tenant_uuid=tenant_uuid,
            wazo_uuid=wazo_uuid,
            identity=inbound.sender,
        )
        recipient_participant = RoomUser(
            uuid=user_uuid,
            tenant_uuid=tenant_uuid,
            wazo_uuid=wazo_uuid,
        )
        room = await self._room_dao.find_or_create_room(
            tenant_uuid=tenant_uuid,
            participants=[sender_participant, recipient_participant],
        )

        message = RoomMessage(
            room_uuid=room.uuid,
            content=inbound.body,
            user_uuid=user_uuid,
            tenant_uuid=tenant_uuid,
            wazo_uuid=wazo_uuid,
        )
        await self._room_dao.add_message(room, message)

        extra: dict[str, str] = {'external_id': inbound.external_id}
        if idempotency_key:
            extra['idempotency_key'] = str(idempotency_key)

        meta = MessageMeta(
            message_uuid=message.uuid,
            backend=inbound.backend,
            extra=extra,
        )
        record = DeliveryRecord(
            message_uuid=message.uuid,
            status=DeliveryStatus.DELIVERED.value,
        )
        await self._room_dao.add_message_meta(meta, record)

        await self._notifier.message_created(room, message)
        logger.info(
            'Inbound message from %s persisted (room=%s)',
            inbound.sender,
            room.uuid,
        )

    _PROVIDER_STATUS_MAP: dict[str, DeliveryStatus] = {
        'sent': DeliveryStatus.SENT,
        'delivered': DeliveryStatus.DELIVERED,
        'failed': DeliveryStatus.FAILED,
        'undelivered': DeliveryStatus.FAILED,
    }

    async def route_status_update(self, update: StatusUpdate) -> None:
        mapped_status = self._PROVIDER_STATUS_MAP.get(update.status)
        if not mapped_status:
            logger.debug(
                'Ignoring transient provider status %r for %s',
                update.status,
                update.external_id,
            )
            return

        meta = await self._room_dao.get_message_meta_by_external_id(
            update.external_id
        )
        if not meta:
            logger.warning(
                'No MessageMeta found for external_id %s, dropping status update',
                update.external_id,
            )
            return

        record = DeliveryRecord(
            message_uuid=meta.message_uuid,
            status=mapped_status.value,
            reason=update.error_code or None,
        )
        self._room_dao.session.add(record)
        await self._room_dao.session.flush()

        await self._notifier.delivery_status_updated(
            message_uuid=str(meta.message_uuid),
            status=mapped_status.value,
            timestamp='',
            backend=update.backend,
            tenant_uuid='',
            room_uuid='',
            user_uuids=[],
        )

        logger.info(
            'Status update: %s → %s (external_id=%s)',
            update.status,
            mapped_status.value,
            update.external_id,
        )

    def _resolve_capabilities(
        self,
        external_participants: list[RoomParticipant],
    ) -> set[str]:
        reachable_types: set[str] = set()
        for participant in external_participants:
            identity = str(participant.identity)
            user_types = self._resolve_reachable_types(identity)
            if not reachable_types:
                reachable_types = user_types
            else:
                reachable_types &= user_types
        return reachable_types

    def _resolve_reachable_types(self, identity: str) -> set[str]:
        reachable: set[str] = set()
        for backend_name in self._registry.available_backends():
            cls = self._registry.get_backend(backend_name)
            instance = cls()
            try:
                instance.normalize_identity(identity)
            except (ValueError, TypeError):
                continue
            reachable.update(cls.supported_types)
        return reachable

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
        connector = self._find_connector(backend)
        if connector is None:
            last_status = DeliveryStatus.DEAD_LETTER
            await self._add_record(
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
                await self._add_record(delivery, last_status)

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
                    await self._add_record(
                        delivery,
                        last_status,
                        reason=f'Max retries ({MAX_RETRIES}) exceeded',
                    )
                else:
                    last_status = DeliveryStatus.RETRYING
                    await self._add_record(delivery, last_status)

        await self._notifier.delivery_status_updated(
            message_uuid=str(delivery.message_uuid),
            status=last_status.value,
            timestamp='',
            backend=backend,
            tenant_uuid=tenant_uuid,
            room_uuid=room_uuid,
            user_uuids=user_uuids or [],
        )

    def _find_connector(self, backend: str) -> Connector | None:
        """Find a connector instance matching the given backend name."""
        logger.debug(
            'Finding connector for backend=%r in %d instances: %s',
            backend,
            len(self._store),
            self._store.backends(),
        )
        return self._store.find_by_backend(backend)

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
    ) -> None:
        record = DeliveryRecord(
            status=status.value,
            reason=reason,
        )
        await self._room_dao.add_delivery_record(delivery, record)
