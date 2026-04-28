# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, exc, func, select
from sqlalchemy.orm import joinedload, selectinload

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageMeta,
    Room,
    RoomMessage,
    RoomUser,
)
from wazo_chatd.exceptions import DuplicateExternalIdException

_UNIQUE_VIOLATION = '23505'

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AsyncRoomDAO:
    @property
    def session(self) -> AsyncSession:
        return get_async_session()

    async def list_pending_external_ids(
        self,
        tenant_uuid: str,
        backend: str,
        limit: int = 100,
    ) -> list[str]:
        """External IDs of outbound messages awaiting a terminal status.

        Filters to messages whose latest :class:`DeliveryRecord` is not
        in ``DELIVERED``, ``FAILED``, or ``DEAD_LETTER``, and that have
        a non-null ``external_id`` (provider has accepted the send).

        Results are ordered oldest-first so a transient backlog catches
        up on subsequent poll cycles without starving older messages.
        """
        terminal = (
            DeliveryStatus.DELIVERED.value,
            DeliveryStatus.FAILED.value,
            DeliveryStatus.DEAD_LETTER.value,
        )
        latest_record = (
            select(
                DeliveryRecord.message_uuid,
                func.max(DeliveryRecord.id).label('max_id'),
            )
            .group_by(DeliveryRecord.message_uuid)
            .subquery()
        )

        stmt = (
            select(MessageMeta.external_id)
            .join(RoomMessage, MessageMeta.message_uuid == RoomMessage.uuid)
            .join(
                latest_record,
                MessageMeta.message_uuid == latest_record.c.message_uuid,
            )
            .join(
                DeliveryRecord,
                DeliveryRecord.id == latest_record.c.max_id,
            )
            .where(RoomMessage.tenant_uuid == tenant_uuid)
            .where(MessageMeta.backend == backend)
            .where(MessageMeta.external_id.isnot(None))
            .where(DeliveryRecord.status.notin_(terminal))
            .order_by(RoomMessage.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_message_meta(self, message_uuid: str) -> MessageMeta | None:
        stmt = (
            select(MessageMeta)
            .options(
                joinedload(MessageMeta.message)
                .joinedload(RoomMessage.room)
                .joinedload(Room.users),
                joinedload(MessageMeta.sender_identity),
            )
            .where(MessageMeta.message_uuid == message_uuid)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_message_meta_by_external_id(
        self, external_id: str, backend: str
    ) -> MessageMeta | None:
        stmt = (
            select(MessageMeta)
            .options(
                selectinload(MessageMeta.records),
                selectinload(MessageMeta.message)
                .selectinload(RoomMessage.room)
                .selectinload(Room.users),
            )
            .where(
                MessageMeta.external_id == external_id,
                MessageMeta.backend == backend,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_delivery_record(
        self,
        meta: MessageMeta,
        status: DeliveryStatus,
        reason: str | None = None,
    ) -> DeliveryRecord:
        record = DeliveryRecord(
            message_uuid=meta.message_uuid,
            status=status.value,
            reason=reason,
        )
        self.session.add(meta)
        self.session.add(record)
        await self.session.flush()
        return record

    async def add_message(self, room: Room, message: RoomMessage) -> RoomMessage:
        message.room_uuid = room.uuid
        self.session.add(message)
        try:
            await self.session.flush()
        except exc.IntegrityError as e:
            await self.session.rollback()
            if (
                getattr(e.orig, 'pgcode', None) == _UNIQUE_VIOLATION
                and message.meta is not None
            ):
                raise DuplicateExternalIdException(
                    str(message.meta.external_id),
                    str(message.meta.backend),
                )
            raise
        return message

    async def add_message_meta(
        self,
        meta: MessageMeta,
        initial_record: DeliveryRecord,
    ) -> MessageMeta:
        self.session.add(meta)
        self.session.add(initial_record)
        await self.session.flush()
        return meta

    async def update_message_meta(self, meta: MessageMeta) -> None:
        self.session.add(meta)
        await self.session.flush()

    async def find_matching_signature(
        self,
        room_uuid: str,
        signature: str,
        window_seconds: int = 60,
    ) -> MessageMeta | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        stmt = (
            select(MessageMeta)
            .join(RoomMessage, MessageMeta.message_uuid == RoomMessage.uuid)
            .options(
                selectinload(MessageMeta.records),
                selectinload(MessageMeta.message)
                .selectinload(RoomMessage.room)
                .selectinload(Room.users),
            )
            .where(RoomMessage.room_uuid == room_uuid)
            .where(
                MessageMeta.extra.op('@>', is_comparison=True)(
                    {'message_signature': signature}
                )
            )
            .where(RoomMessage.created_at > cutoff)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def check_duplicate_idempotency_key(
        self,
        idempotency_key: str,
    ) -> bool:
        stmt = select(MessageMeta.message_uuid).where(
            MessageMeta.extra.op('@>', is_comparison=True)(
                {'inbound_idempotency_key': idempotency_key}
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def find_room(
        self,
        tenant_uuid: str,
        participants: list[RoomUser],
    ) -> Room | None:
        participant_uuids = [p.uuid for p in participants]
        n = len(participant_uuids)

        exact_match = (
            select(RoomUser.room_uuid)
            .group_by(RoomUser.room_uuid)
            .having(
                and_(
                    func.count() == n,
                    func.count(func.nullif(RoomUser.uuid.in_(participant_uuids), False))
                    == n,
                )
            )
        ).subquery()

        stmt = (
            select(Room)
            .options(selectinload(Room.users))
            .where(
                Room.tenant_uuid == tenant_uuid,
                Room.uuid.in_(select(exact_match.c.room_uuid)),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_room(
        self,
        tenant_uuid: str,
        participants: list[RoomUser],
    ) -> Room:
        room = Room(tenant_uuid=tenant_uuid, users=participants)
        self.session.add(room)
        await self.session.flush()
        return room

    async def get_recoverable_messages(
        self,
    ) -> list[tuple[MessageMeta, str]]:
        latest_record = (
            select(
                DeliveryRecord.message_uuid,
                func.max(DeliveryRecord.id).label('max_id'),
            )
            .group_by(DeliveryRecord.message_uuid)
            .subquery()
        )

        stmt = (
            select(MessageMeta, DeliveryRecord.status)
            .join(
                latest_record,
                MessageMeta.message_uuid == latest_record.c.message_uuid,
            )
            .join(
                DeliveryRecord,
                DeliveryRecord.id == latest_record.c.max_id,
            )
            .options(
                selectinload(MessageMeta.message)
                .selectinload(RoomMessage.room)
                .selectinload(Room.users)
            )
            .where(
                DeliveryRecord.status.in_(
                    [
                        DeliveryStatus.PENDING.value,
                        DeliveryStatus.RETRYING.value,
                    ]
                )
            )
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
