# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from wazo_chatd.database.async_helpers import get_async_session
from wazo_chatd.database.models import User, UserIdentity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AsyncUserIdentityDAO:
    @property
    def session(self) -> AsyncSession:
        return get_async_session()

    async def find_by_identity_and_backend(
        self,
        identity: str,
        backend: str,
    ) -> UserIdentity | None:
        stmt = (
            select(UserIdentity)
            .options(selectinload(UserIdentity.user))
            .where(
                UserIdentity.identity == identity,
                UserIdentity.backend == backend,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def resolve_users_by_identities(
        self,
        identities: list[str],
        backend: str | None = None,
    ) -> dict[str, User]:
        stmt = (
            select(UserIdentity)
            .options(selectinload(UserIdentity.user))
            .where(UserIdentity.identity.in_(identities))
        )
        if backend:
            stmt = stmt.where(UserIdentity.backend == backend)
        result = await self.session.execute(stmt)
        return {str(record.identity): record.user for record in result.scalars().all()}

    async def list_tenant_backends(self) -> list[tuple[str, str]]:
        stmt = select(UserIdentity.tenant_uuid, UserIdentity.backend).distinct()
        result = await self.session.execute(stmt)
        return [(str(row[0]), row[1]) for row in result.all()]

    async def list_by_user(
        self,
        user_uuid: str,
        tenant_uuids: Iterable[str] | None = None,
        backends: Iterable[str] | None = None,
    ) -> list[UserIdentity]:
        stmt = select(UserIdentity).where(
            UserIdentity.user_uuid == user_uuid,
        )
        if tenant_uuids is not None:
            stmt = stmt.where(UserIdentity.tenant_uuid.in_(tenant_uuids))
        if backends:
            stmt = stmt.where(UserIdentity.backend.in_(backends))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
