# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from wazo_chatd.database.models import DeliveryRecord, MessageMeta, Room, RoomUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def add_message_meta(
    session: AsyncSession,
    meta: MessageMeta,
    initial_record: DeliveryRecord,
) -> None:
    session.add(meta)
    session.add(initial_record)
    await session.flush()


async def find_or_create_room(
    session: AsyncSession,
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

    stmt = select(Room).filter(
        Room.tenant_uuid == tenant_uuid,
        Room.uuid.in_(select(exact_match.c.room_uuid)),
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    room = Room(tenant_uuid=tenant_uuid, users=participants)
    session.add(room)
    await session.flush()
    return room


async def check_duplicate_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> bool:
    stmt = select(MessageMeta.message_uuid).filter(
        MessageMeta.extra.op('@>', is_comparison=True)(
            {'idempotency_key': idempotency_key}
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
