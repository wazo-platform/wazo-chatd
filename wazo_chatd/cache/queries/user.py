# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache import get_local_cache
from wazo_chatd.cache.models import (
    CachedUser,
    CachedSession,
    CachedLine,
    CachedRefreshToken,
)
from wazo_chatd.database.models import User, Session, Line, RefreshToken
from wazo_chatd.exceptions import UnknownUserException


class UserCache:
    @property
    def cache(self):
        return get_local_cache()

    @property
    def users(self):
        return get_local_cache().values()

    def get_user(self, user_uuid: str):
        user_uuid = str(user_uuid)
        try:
            return self.cache[user_uuid]
        except KeyError:
            raise UnknownUserException(user_uuid)

    def count(self, tenant_uuids, **filter_parameters):
        return len(self._filter_users(tenant_uuids, **filter_parameters))

    def create(self, user: User):
        user_uuid = str(user.uuid)
        self.cache[user_uuid] = CachedUser.from_sql(user)
        return user

    def delete(self, user: User):
        user_uuid = str(user.uuid)
        self.cache.pop(user_uuid, None)

    def get(self, tenant_uuids, user_uuid: str):
        tenant_uuids = [str(tenant_uuid) for tenant_uuid in tenant_uuids]
        user = self.get_user(user_uuid)
        if user.tenant_uuid not in tenant_uuids:
            raise UnknownUserException(user_uuid)
        return self.from_cache(user)

    def list_(self, tenant_uuids, uuids=None, **filters):
        return self._filter_users(tenant_uuids=tenant_uuids, uuids=uuids)

    def update(self, user: User):
        user_uuid = str(user.uuid)
        self.cache[user_uuid] = CachedUser.from_sql(user)

    def add_session(self, user: User, session: Session):
        user_uuid = str(user.uuid)
        session_uuid = str(session.uuid)
        sessions = self.get_user(user_uuid).sessions

        for existing_session in sessions:
            if existing_session.uuid == session_uuid:
                sessions.remove(existing_session)
        else:
            sessions.append(CachedSession.from_sql(session))

    def remove_session(self, user: User, session: Session):
        user_uuid = str(user.uuid)
        session_uuid = str(session.uuid)
        sessions = self.get_user(user_uuid).sessions

        for existing_session in sessions:
            if existing_session.uuid == session_uuid:
                sessions.remove(session)
                return

    def add_line(self, user: User, line: Line):
        user_uuid = str(user.uuid)
        line_id = int(line.id)
        lines = self.get_user(user_uuid).lines

        for existing_line in lines:
            if existing_line.id == line_id:
                return
        else:
            line = CachedLine.from_sql(line)
            line.user_uuid = user_uuid
            line.tenant_uuid = str(user.tenant_uuid)
            lines.append(line)

    def remove_line(self, user: User, line: Line):
        user_uuid = str(user.uuid)
        line_id = int(line.id)
        lines = self.get_user(user_uuid).lines

        for existing_line in lines:
            if existing_line.id == line_id:
                lines.remove(existing_line)
                return

    def add_refresh_token(self, user: User, refresh_token: RefreshToken):
        user_uuid = str(user.uuid)
        client_id = str(refresh_token.client_id)
        tokens = self.get_user(user_uuid).refresh_tokens

        for existing_token in tokens:
            if existing_token.client_id == client_id:
                tokens.remove(existing_token)
        else:
            tokens.append(CachedRefreshToken.from_sql(refresh_token))

    def remove_refresh_token(self, user: User, refresh_token: RefreshToken):
        user_uuid = str(user.uuid)
        client_id = str(refresh_token.client_id)
        tokens = self.get_user(user_uuid).refresh_tokens

        for existing_token in tokens:
            if existing_token.client_id == client_id:
                tokens.remove(existing_token)

    def _filter_users(self, tenant_uuids=None, uuids=None):
        users = self.users
        uuids = [str(uuid) for uuid in uuids or []]
        tenant_uuids = [str(tenant_uuid) for tenant_uuid in tenant_uuids or []]

        if uuids:
            users = [user for user in users if user.uuid in uuids]

        if tenant_uuids is None:
            return [self.from_cache(user) for user in users]

        if tenant_uuids:
            return [
                self.from_cache(user)
                for user in users
                if user.tenant_uuid in tenant_uuids
            ]

        return []

    @staticmethod
    def from_cache(user: CachedUser):
        return user
