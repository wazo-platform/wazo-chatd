# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import (
    CachedUser,
    CachedSession,
    CachedLine,
    CachedRefreshToken,
)
from wazo_chatd.database.models import User, Session, Line, RefreshToken
from wazo_chatd.exceptions import UnknownUserException


class UserCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def count(self, tenant_uuids: list[str], **filter_parameters):
        return len(self._filter_users(tenant_uuids, **filter_parameters))

    def create(self, user: User):
        CachedUser.from_sql(user).store(self._cache)
        return user

    def delete(self, user: User):
        CachedUser.restore(self._cache, user.uuid).remove()

    def get(self, tenant_uuids: list[str], user_uuid: str):
        tenant_uuids = [str(tenant_uuid) for tenant_uuid in tenant_uuids]
        try:
            user = CachedUser.restore(self._cache, user_uuid)
        except ValueError:
            raise UnknownUserException(user_uuid)
        else:
            if user.tenant_uuid not in tenant_uuids:
                raise UnknownUserException(user_uuid)
        return user

    def list_(self, tenant_uuids: list[str], uuids: list[str] = None, **filters):
        return self._filter_users(tenant_uuids=tenant_uuids, uuids=uuids)

    def update(self, user: User):
        CachedUser.from_sql(user).store(self._cache)

    def add_session(self, user: User, session: Session):
        cached_user = CachedUser.restore(self._cache, user.uuid)
        sessions = cached_user.sessions

        for existing_session in sessions:
            if existing_session.uuid == str(session.uuid):
                sessions.remove(existing_session)
        else:
            session = CachedSession(
                session.uuid,
                session.mobile,
                session.user_uuid,
                session.tenant_uuid,
            )
            sessions.append(session)
        cached_user.store(self._cache)

    def remove_session(self, user: User, session: Session):
        user_uuid = str(user.uuid)
        session_uuid = str(session.uuid)

        cached_user = CachedUser.restore(self._cache, user_uuid)
        sessions = cached_user.sessions

        for existing_session in sessions:
            if existing_session.uuid == session_uuid:
                sessions.remove(session)
                cached_user.store(self._cache)
                return

    def add_line(self, user: User, line: Line):
        user_uuid = str(user.uuid)
        line_id = int(line.id)
        cached_user = CachedUser.restore(self._cache, user_uuid)

        for existing_line in cached_user.lines:
            if existing_line.id == line_id:
                return
        else:
            line = CachedLine(
                line.id, str(user.uuid), None, None, str(user.tenant_uuid)
            )
            cached_user.lines.append(line)
            cached_user.store(self._cache)

    def remove_line(self, user: User, line: Line):
        user_uuid = str(user.uuid)
        line_id = int(line.id)
        cached_user = CachedUser.restore(self._cache, user_uuid)

        for existing_line in cached_user.lines:
            if existing_line.id == line_id:
                cached_user.lines.remove(existing_line)
                cached_user.store(self._cache)
                return

    def add_refresh_token(self, user: User, refresh_token: RefreshToken):
        user_uuid = str(user.uuid)
        client_id = str(refresh_token.client_id)
        cached_user = CachedUser.restore(self._cache, user_uuid)

        for existing_token in cached_user.refresh_tokens:
            if existing_token.client_id == client_id:
                return
        else:
            token = CachedRefreshToken(
                refresh_token.client_id,
                str(refresh_token.user_uuid),
                refresh_token.mobile,
                refresh_token.tenant_uuid,
            )
            cached_user.refresh_tokens.append(token)
            cached_user.store(self._cache)

    def remove_refresh_token(self, user: User, refresh_token: RefreshToken):
        user_uuid = str(user.uuid)
        client_id = str(refresh_token.client_id)
        cached_user = CachedUser.restore(self._cache, user_uuid)

        for existing_token in cached_user.refresh_tokens:
            if existing_token.client_id == client_id:
                cached_user.refresh_tokens.remove(existing_token)
                cached_user.store(self._cache)

    def _filter_users(self, tenant_uuids: list[str] = None, uuids: list[str] = None):
        users = CachedUser.all(self._cache)

        if uuids:
            uuids = [str(uuid) for uuid in uuids or []]
            users = [user for user in users if user.uuid in uuids]

        if tenant_uuids is None:
            return users

        if tenant_uuids:
            tenant_uuids = [str(tenant_uuid) for tenant_uuid in tenant_uuids or []]
            return [user for user in users if user.tenant_uuid in tenant_uuids]

        return []
