# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import exc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from wazo_chatd.database.models import Tenant, User, UserIdentity
from wazo_chatd.exceptions import (
    DuplicateIdentityException,
    UnknownUserIdentityException,
)

_UNIQUE_VIOLATION = '23505'


class UserIdentityDAO:
    def __init__(self, session):  # type: ignore[no-untyped-def]
        self._session = session

    @property
    def session(self) -> Session:
        return self._session()

    def ensure_tenant_and_user_exist(self, tenant_uuid: str, user_uuid: str) -> None:
        self.session.execute(
            pg_insert(Tenant).values(uuid=tenant_uuid).on_conflict_do_nothing()
        )
        self.session.execute(
            pg_insert(User)
            .values(uuid=user_uuid, tenant_uuid=tenant_uuid, state='unavailable')
            .on_conflict_do_nothing()
        )

    def create(self, identity: UserIdentity) -> UserIdentity:
        self.session.add(identity)
        try:
            self.session.flush()
        except exc.IntegrityError as e:
            self.session.rollback()
            if e.orig.pgcode == _UNIQUE_VIOLATION:
                raise DuplicateIdentityException(
                    identity.backend, identity.identity, identity.type_  # type: ignore[arg-type]
                )
            raise

        return identity

    def get(
        self,
        tenant_uuids: Iterable[str],
        identity_uuid: str,
        user_uuid: str | None = None,
    ) -> UserIdentity:
        stmt = select(UserIdentity).where(
            UserIdentity.tenant_uuid.in_(tenant_uuids),
            UserIdentity.uuid == identity_uuid,
        )
        if user_uuid is not None:
            stmt = stmt.where(UserIdentity.user_uuid == user_uuid)

        if not (result := self.session.execute(stmt).scalars().first()):
            raise UnknownUserIdentityException(identity_uuid)
        return result

    def find(self, identity_uuid: str) -> UserIdentity | None:
        stmt = select(UserIdentity).where(UserIdentity.uuid == identity_uuid)
        return self.session.execute(stmt).scalars().first()

    def list_by_user(
        self,
        user_uuid: str,
        tenant_uuids: Iterable[str] | None = None,
        backends: Iterable[str] | None = None,
        types: Iterable[str] | None = None,
    ) -> list[UserIdentity]:
        stmt = select(UserIdentity).where(
            UserIdentity.user_uuid == user_uuid,
        )
        if tenant_uuids is not None:
            stmt = stmt.where(UserIdentity.tenant_uuid.in_(tenant_uuids))
        if backends:
            stmt = stmt.where(UserIdentity.backend.in_(backends))
        if types:
            stmt = stmt.where(UserIdentity.type_.in_(types))

        return list(self.session.execute(stmt).scalars().all())

    def update(self, identity: UserIdentity) -> None:
        self.session.add(identity)
        self.session.flush()

    def delete(self, identity: UserIdentity) -> None:
        self.session.delete(identity)
        self.session.flush()

    def list_types_by_users(
        self,
        user_uuids: list[str],
    ) -> dict[str, set[str]]:
        stmt = (
            select(UserIdentity.user_uuid, UserIdentity.type_)
            .where(UserIdentity.user_uuid.in_(user_uuids))
            .distinct()
        )

        rows = self.session.execute(stmt).all()
        result: dict[str, set[str]] = {uid: set() for uid in user_uuids}

        for user_uuid_val, type_ in rows:
            result[str(user_uuid_val)].add(type_)

        return result

    def list_bound_identities(self, identities: Iterable[str]) -> set[str]:
        stmt = (
            select(UserIdentity.identity)
            .where(UserIdentity.identity.in_(identities))
            .distinct()
        )
        return set(self.session.execute(stmt).scalars().all())

    def is_identity_bound(self, identity: str) -> bool:
        stmt = select(UserIdentity).where(UserIdentity.identity == identity)
        return self.session.execute(stmt).scalars().first() is not None

    def resolve_users_by_identities(
        self,
        identities: Iterable[str],
    ) -> dict[str, User]:
        stmt = (
            select(UserIdentity)
            .options(selectinload(UserIdentity.user))
            .where(UserIdentity.identity.in_(list(identities)))
        )
        return {
            str(r.identity): r.user for r in self.session.execute(stmt).scalars().all()
        }

    def list_tenant_backends(self) -> list[tuple[str, str]]:
        stmt = select(UserIdentity.tenant_uuid, UserIdentity.backend).distinct()
        return list(self.session.execute(stmt).all())  # type: ignore[arg-type]
