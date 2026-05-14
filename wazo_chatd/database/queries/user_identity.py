# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import exc, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select

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
        statement = select(UserIdentity).where(
            UserIdentity.tenant_uuid.in_(tenant_uuids),
            UserIdentity.uuid == identity_uuid,
        )
        if user_uuid is not None:
            statement = statement.where(UserIdentity.user_uuid == user_uuid)

        if not (result := self.session.execute(statement).scalars().first()):
            raise UnknownUserIdentityException(identity_uuid)
        return result

    def find(
        self, identity_uuid: str | UUID, user_uuid: str | None = None
    ) -> UserIdentity | None:
        statement = select(UserIdentity).where(UserIdentity.uuid == identity_uuid)
        if user_uuid is not None:
            statement = statement.where(UserIdentity.user_uuid == user_uuid)
        return self.session.execute(statement).scalars().first()

    def update(self, identity: UserIdentity) -> None:
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

    def delete(self, identity: UserIdentity) -> None:
        self.session.delete(identity)
        self.session.flush()

    def list_(
        self,
        tenant_uuids: Iterable[str] | None = None,
        user_uuid: str | None = None,
        backends: Iterable[str] | None = None,
        types: Iterable[str] | None = None,
        **filter_parameters: Any,
    ) -> list[UserIdentity]:
        statement = self._build_list_query(tenant_uuids, user_uuid, backends, types)
        statement = self._list_filter(statement, **filter_parameters)
        statement = self._paginate(statement, **filter_parameters)

        return list(self.session.execute(statement).scalars().all())

    def count(
        self,
        tenant_uuids: Iterable[str] | None = None,
        user_uuid: str | None = None,
        backends: Iterable[str] | None = None,
        types: Iterable[str] | None = None,
        **filter_parameters: Any,
    ) -> int:
        statement = self._build_list_query(tenant_uuids, user_uuid, backends, types)
        statement = self._list_filter(statement, **filter_parameters)

        count_statement = select(func.count()).select_from(statement.subquery())
        return int(self.session.execute(count_statement).scalar_one())

    def find_tenant_by_identity(self, identity: str, backend: str) -> str | None:
        statement = (
            select(UserIdentity.tenant_uuid)
            .where(
                UserIdentity.identity == identity,
                UserIdentity.backend == backend,
            )
            .limit(1)
        )
        result = self.session.execute(statement).scalars().first()
        return str(result) if result is not None else None

    def has_identities_for_backend(self, tenant_uuid: str, backend: str) -> bool:
        statement = select(
            exists()
            .where(UserIdentity.tenant_uuid == tenant_uuid)
            .where(UserIdentity.backend == backend)
        )
        return bool(self.session.execute(statement).scalar_one())

    def list_bound_identities(self, identities: Iterable[str]) -> set[str]:
        statement = (
            select(UserIdentity.identity)
            .where(UserIdentity.identity.in_(identities))
            .distinct()
        )
        return set(self.session.execute(statement).scalars().all())

    def list_identities_by_users(
        self,
        user_uuids: Iterable[str],
        backend: str,
    ) -> dict[str, str]:
        statement = select(UserIdentity.user_uuid, UserIdentity.identity).where(
            UserIdentity.user_uuid.in_(list(user_uuids)),
            UserIdentity.backend == backend,
        )
        return {
            str(user_uuid): str(identity)
            for user_uuid, identity in self.session.execute(statement).all()
        }

    def list_tenant_backends(self) -> list[tuple[str, str]]:
        statement = select(UserIdentity.tenant_uuid, UserIdentity.backend).distinct()
        return list(self.session.execute(statement).all())  # type: ignore[arg-type]

    def list_types_by_users(
        self,
        user_uuids: list[str],
    ) -> dict[str, set[str]]:
        statement = (
            select(UserIdentity.user_uuid, UserIdentity.type_)
            .where(UserIdentity.user_uuid.in_(user_uuids))
            .distinct()
        )

        rows = self.session.execute(statement).all()
        result: dict[str, set[str]] = {uid: set() for uid in user_uuids}

        for user_uuid_val, type_ in rows:
            result[str(user_uuid_val)].add(type_)

        return result

    def resolve_users_by_identities(
        self,
        identities: Iterable[str],
    ) -> dict[str, User]:
        statement = (
            select(UserIdentity)
            .options(selectinload(UserIdentity.user))
            .where(UserIdentity.identity.in_(list(identities)))
        )
        return {
            str(r.identity): r.user
            for r in self.session.execute(statement).scalars().all()
        }

    def _build_list_query(
        self,
        tenant_uuids: Iterable[str] | None,
        user_uuid: str | None,
        backends: Iterable[str] | None,
        types: Iterable[str] | None,
    ) -> Select:
        statement = select(UserIdentity)

        if tenant_uuids is not None:
            statement = statement.where(UserIdentity.tenant_uuid.in_(tenant_uuids))

        if user_uuid is not None:
            statement = statement.where(UserIdentity.user_uuid == user_uuid)

        if backends:
            statement = statement.where(UserIdentity.backend.in_(backends))

        if types:
            statement = statement.where(UserIdentity.type_.in_(types))

        return statement

    def _list_filter(
        self,
        statement: Select,
        search: str | None = None,
        user_uuids: list[str] | None = None,
        backend: str | None = None,
        type_: str | None = None,
        identity: str | None = None,
        **_: Any,
    ) -> Select:
        if search is not None:
            statement = statement.where(
                func.lower(UserIdentity.identity).contains(
                    search.lower(), autoescape=True
                )
            )

        if user_uuids:
            statement = statement.where(UserIdentity.user_uuid.in_(user_uuids))

        if backend is not None:
            statement = statement.where(UserIdentity.backend == backend)

        if type_ is not None:
            statement = statement.where(UserIdentity.type_ == type_)

        if identity is not None:
            statement = statement.where(UserIdentity.identity == identity)

        return statement

    def _paginate(
        self,
        statement: Select,
        limit: int | None = None,
        offset: int | None = None,
        order: str = 'identity',
        direction: str = 'asc',
        **_: Any,
    ) -> Select:
        column_name = 'type_' if order == 'type' else order
        order_column = getattr(UserIdentity, column_name)
        order_column = order_column.asc() if direction == 'asc' else order_column.desc()
        statement = statement.order_by(order_column)

        if limit is not None:
            statement = statement.limit(limit)

        if offset is not None:
            statement = statement.offset(offset)

        return statement
