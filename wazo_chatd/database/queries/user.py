# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import Boolean, text
from sqlalchemy_utils import UUIDType

from ...exceptions import UnknownUserException
from ..helpers import bulk_delete, bulk_insert, bulk_update
from ..models import User


class UserDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def create(self, user):
        self.session.add(user)
        self.session.flush()
        return user

    def create_all(self, users: list[User]) -> None:
        bulk_insert(self.session, users)

    def update(self, user):
        self.session.add(user)
        self.session.flush()

    def get(self, tenant_uuids, user_uuid):
        query = self.session.query(User).filter(
            User.tenant_uuid.in_(tenant_uuids), User.uuid == user_uuid
        )

        user = query.first()
        if not user:
            raise UnknownUserException(user_uuid)
        return user

    def list_(self, tenant_uuids, uuids=None, **filter_parameters):
        query = self._get_users_query(
            tenant_uuids,
            uuids=uuids,
            **filter_parameters,
        )
        return query.all()

    def count(self, tenant_uuids, **filter_parameters):
        return self._get_users_query(tenant_uuids, **filter_parameters).count()

    def list_uuids(self) -> set[str]:
        return {str(uuid) for (uuid,) in self.session.query(User.uuid).all()}

    def list_uuids_with_tenant_uuids(self) -> list[tuple[UUID, UUID]]:
        return self.session.query(User.uuid, User.tenant_uuid).all()

    def list_dnd(self) -> dict[str, bool]:
        return {
            str(uuid): dnd
            for uuid, dnd in self.session.query(User.uuid, User.do_not_disturb).all()
        }

    def delete(self, user):
        self.session.delete(user)
        self.session.flush()

    def delete_by_uuids(self, uuids: Sequence[str]) -> None:
        bulk_delete(self.session, User, User.uuid, uuids)

    def update_dnd(self, dnd_by_uuid: Iterable[tuple[str, bool]]) -> None:
        bulk_update(
            self.session,
            User,
            columns=[('uuid', UUIDType()), ('do_not_disturb', Boolean)],
            rows=list(dnd_by_uuid),
            key_columns=['uuid'],
        )

    def _get_users_query(self, tenant_uuids=None, uuids=None):
        query = self.session.query(User)

        if uuids:
            query = query.filter(User.uuid.in_(uuids))

        if tenant_uuids is None:
            return query

        if not tenant_uuids:
            return query.filter(text('false'))

        return query.filter(User.tenant_uuid.in_(tenant_uuids))

    def add_session(self, user, session):
        if session in user.sessions:
            return

        for existing_session in user.sessions:
            if existing_session.uuid == session.uuid:
                user.sessions.remove(existing_session)

        user.sessions.append(session)
        self.session.flush()

    def remove_session(self, user, session):
        if session in user.sessions:
            user.sessions.remove(session)
            self.session.flush()

    def add_line(self, user, line):
        if line not in user.lines:
            user.lines.append(line)
            self.session.flush()

    def remove_line(self, user, line):
        if line in user.lines:
            user.lines.remove(line)
            self.session.flush()

    def add_refresh_token(self, user, refresh_token):
        if refresh_token in user.refresh_tokens:
            return

        for existing_token in user.refresh_tokens:
            if existing_token.client_id == refresh_token.client_id:
                user.refresh_tokens.remove(existing_token)

        user.refresh_tokens.append(refresh_token)
        self.session.flush()

    def remove_refresh_token(self, user, refresh_token):
        if refresh_token in user.refresh_tokens:
            user.refresh_tokens.remove(refresh_token)
            self.session.flush()
