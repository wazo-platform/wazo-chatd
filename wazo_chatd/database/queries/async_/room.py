# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select
from sqlalchemy.orm import selectinload

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageMeta,
    Room,
    RoomMessage,
    RoomUser,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AsyncRoomDAO:
    @property
    def session(self) -> AsyncSession:
        return get_async_session()

    async def get_message_meta(self, message_uuid: str) -> MessageMeta | None:
        stmt = select(MessageMeta).filter(MessageMeta.message_uuid == message_uuid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_message_meta_by_external_id(
        self, external_id: str
    ) -> MessageMeta | None:
        stmt = (
            select(MessageMeta)
            .options(
                selectinload(MessageMeta.message)
                .selectinload(RoomMessage.room)
                .selectinload(Room.users)
            )
            .filter(MessageMeta.external_id == external_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_delivery_record(
        self,
        meta: MessageMeta,
        record: DeliveryRecord,
    ) -> DeliveryRecord:
        record.message_uuid = meta.message_uuid
        self.session.add(record)
        await self.session.flush()
        return record

    async def add_message(self, room: Room, message: RoomMessage) -> RoomMessage:
        message.room_uuid = room.uuid
        self.session.add(message)
        await self.session.flush()
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

    async def check_duplicate_idempotency_key(
        self,
        idempotency_key: str,
    ) -> bool:
        stmt = select(MessageMeta.message_uuid).filter(
            MessageMeta.extra.op('@>', is_comparison=True)(
                {'idempotency_key': idempotency_key}
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def find_or_create_room(
        self,
        tenant_uuid: str,
        participants: list[RoomUser],
    ) -> Room:
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
            .filter(
                Room.tenant_uuid == tenant_uuid,
                Room.uuid.in_(select(exact_match.c.room_uuid)),
            )
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

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
            .filter(
                DeliveryRecord.status.in_(
                    [
                        DeliveryStatus.PENDING.value,
                        DeliveryStatus.SENDING.value,
                        DeliveryStatus.RETRYING.value,
                    ]
                )
            )
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
