# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from wazo_chatd.database.models import ChatProvider, UserAlias

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def find_by_identity_and_backend(
    session: AsyncSession,
    identity: str,
    backend: str,
) -> UserAlias | None:
    stmt = (
        select(UserAlias)
        .join(ChatProvider)
        .options(selectinload(UserAlias.provider))
        .filter(UserAlias.identity == identity, ChatProvider.backend == backend)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_user_and_types(
    session: AsyncSession,
    user_uuid: str,
    types: list[str] | None = None,
) -> list[UserAlias]:
    stmt = (
        select(UserAlias)
        .options(selectinload(UserAlias.provider))
        .filter(UserAlias.user_uuid == user_uuid)
    )

    if types:
        stmt = stmt.join(ChatProvider).filter(ChatProvider.type_.in_(types))

    result = await session.execute(stmt)
    return list(result.scalars().all())
