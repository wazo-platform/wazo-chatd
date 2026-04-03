# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.models import ChatProvider, User, UserAlias

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AsyncUserAliasDAO:
    @property
    def session(self) -> AsyncSession:
        return get_async_session()

    async def find_by_identity_and_backend(
        self,
        identity: str,
        backend: str,
    ) -> UserAlias | None:
        stmt = (
            select(UserAlias)
            .join(ChatProvider)
            .options(
                selectinload(UserAlias.provider),
                selectinload(UserAlias.user),
            )
            .filter(UserAlias.identity == identity, ChatProvider.backend == backend)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def resolve_users_by_identities(
        self, identities: list[str],
    ) -> dict[str, User]:
        stmt = (
            select(UserAlias)
            .options(selectinload(UserAlias.user))
            .filter(UserAlias.identity.in_(identities))
        )
        result = await self.session.execute(stmt)
        return {str(alias.identity): alias.user for alias in result.scalars().all()}

    async def list_by_user_and_types(
        self,
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

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
