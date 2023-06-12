# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import (
    CachedUser,
    CachedSession,
    CachedLine,
    CachedRefreshToken,
)
from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import (
    User as SQLUser,
    Line as SQLLine,
    RefreshToken as SQLRefreshToken,
)
from wazo_chatd.exceptions import UnknownUserException

logger = logging.getLogger(__name__)


class UserCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def count(self, tenant_uuids: list[str], **filter_parameters):
        return len(self._filter_users(tenant_uuids, **filter_parameters))

    def create(self, user: SQLUser, persist=True):
        CachedUser.from_sql(user).save(self._cache)

        if persist:
            with session_scope() as session:
                session.add(user)
                session.flush()

        return user

    def delete(self, user: SQLUser, persist: bool = True):
        CachedUser.load(self._cache, user.uuid).delete(self._cache)
        if persist:
            with session_scope() as session:
                session.query(SQLUser).filter_by(uuid=user.uuid).delete()
                session.flush()

    def get(self, tenant_uuids: list[str], user_uuid: str):
        tenant_uuids = [str(tenant_uuid) for tenant_uuid in tenant_uuids]
        try:
            user = CachedUser.load(self._cache, user_uuid)
        except ValueError:
            raise UnknownUserException(user_uuid)
        else:
            if user.tenant_uuid not in tenant_uuids:
                logger.debug(
                    'Tenant mismatch for user %s: looking for tenants %s, found tenant %s in cache',
                    user_uuid,
                    tenant_uuids,
                    user.tenant_uuid,
                )
                raise UnknownUserException(user_uuid)
        return user

    def list_(self, tenant_uuids: list[str], uuids: list[str] = None, **filters):
        return self._filter_users(tenant_uuids=tenant_uuids, uuids=uuids)

    def update(self, user: CachedUser, persist: bool = True):
        user.save(self._cache)

        if persist:
            with session_scope() as session:
                db_user = (
                    session.query(SQLUser)
                    .filter_by(tenant_uuid=user.tenant_uuid, uuid=user.uuid)
                    .first()
                )
                if not db_user:
                    logger.error(
                        'update failed, user not found in database: tenant %s, user %s',
                        user.tenant_uuid,
                        user.uuid,
                    )
                    raise UnknownUserException(user.uuid)
                db_user.state = user.state
                db_user.status = user.status
                db_user.last_activity = user.last_activity
                session.add(db_user)
                session.flush()

    def add_session(self, user: CachedUser, session: CachedSession):
        for existing_session in user.sessions:
            if existing_session.uuid == str(session.uuid):
                return

        session = CachedSession(
            session.uuid,
            session.mobile,
            user.uuid,
            user.tenant_uuid,
        )
        user.sessions.append(session)
        user.save(self._cache)

    def remove_session(self, user: CachedUser, session: CachedSession):
        for existing_session in user.sessions:
            if existing_session.uuid == session.uuid:
                user.sessions.remove(existing_session)
                session.delete(self._cache)
                user.save(self._cache)
                return

    def add_line(self, user: CachedUser, line: SQLLine):
        for existing_line in user.lines:
            if existing_line.id == int(line.id):
                return
        else:
            line = CachedLine(line.id, user.uuid, None, None, user.tenant_uuid)
            user.lines.append(line)
            user.save(self._cache)

    def remove_line(self, user: CachedUser, line: CachedLine):
        for existing_line in user.lines:
            if existing_line.id == line.id:
                user.lines.remove(existing_line)
                line.delete(self._cache)
                user.save(self._cache)
                return

    def add_refresh_token(self, user: CachedUser, refresh_token: SQLRefreshToken):
        user_uuid = str(refresh_token.user_uuid)
        client_id = str(refresh_token.client_id)

        for existing_token in user.refresh_tokens:
            if (
                existing_token.user_uuid == user_uuid
                and existing_token.client_id == client_id
            ):
                return
        else:
            token = CachedRefreshToken(
                refresh_token.client_id,
                user.uuid,
                refresh_token.mobile,
                user.tenant_uuid,
            )
            user.refresh_tokens.append(token)
            user.save(self._cache)

    def remove_refresh_token(self, user: CachedUser, refresh_token: CachedRefreshToken):
        for existing_token in user.refresh_tokens:
            if (
                existing_token.user_uuid == refresh_token.user_uuid
                and existing_token.client_id == refresh_token.client_id
            ):
                user.refresh_tokens.remove(existing_token)
                refresh_token.delete(self._cache)
                user.save(self._cache)

    def _filter_users(self, tenant_uuids: list[str] = None, uuids: list[str] = None):
        users = CachedUser.load_all(self._cache)

        if uuids:
            uuids = [str(uuid) for uuid in uuids or []]
            users = [user for user in users if user.uuid in uuids]

        if tenant_uuids is None:
            return users

        if tenant_uuids:
            tenant_uuids = [str(tenant_uuid) for tenant_uuid in tenant_uuids or []]
            return [user for user in users if user.tenant_uuid in tenant_uuids]

        return []
