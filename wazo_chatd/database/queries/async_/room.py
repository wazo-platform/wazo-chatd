# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from wazo_chatd.database.async_helpers import get_async_session
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

    async def add_delivery_record(
        self,
        meta: MessageMeta,
        record: DeliveryRecord,
    ) -> None:
        meta.records.append(record)
        await self.session.flush()

    async def add_message(self, room: Room, message: RoomMessage) -> None:
        # Set FK directly instead of room.messages.append() to avoid
        # lazy-loading the messages collection (triggers MissingGreenlet
        # in async context)
        message.room_uuid = room.uuid
        self.session.add(message)
        await self.session.flush()

    async def add_message_meta(
        self,
        meta: MessageMeta,
        initial_record: DeliveryRecord,
    ) -> None:
        self.session.add(meta)
        self.session.add(initial_record)
        await self.session.flush()

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
                    func.count(
                        func.nullif(RoomUser.uuid.in_(participant_uuids), False)
                    )
                    == n,
                )
            )
        ).subquery()

        stmt = select(Room).filter(
            Room.tenant_uuid == tenant_uuid,
            Room.uuid.in_(select(exact_match.c.room_uuid)),
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        room = Room(tenant_uuid=tenant_uuid, users=participants)
        self.session.add(room)
        await self.session.flush()
        return room
