# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedSession, CachedUser
from wazo_chatd.database.models import Session
from wazo_chatd.exceptions import UnknownSessionException


class SessionCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def get(self, session_uuid: str):
        try:
            return CachedSession.restore(self._cache, session_uuid)
        except ValueError:
            raise UnknownSessionException(session_uuid)

    def find(self, session_uuid: str):
        try:
            return CachedSession.restore(self._cache, session_uuid)
        except ValueError:
            return None

        # session_uuid = str(session_uuid)
        # sessions = CachedSession.all(self._cache)

        # if session_uuid:
        #     sessions = [session for session in sessions if session.uuid == session_uuid]

        # return sessions[0] if sessions else None

    def list_(self):
        return CachedSession.all(self._cache)

    def update(self, session: Session):
        user_uuid = str(session.user_uuid)
        cached_user = CachedUser.restore(self._cache, user_uuid)
        session_data = CachedSession.from_sql(session)

        for existing_session in cached_user.sessions:
            if existing_session.uuid == str(session.uuid):
                existing_session = session_data
                cached_user.store(self._cache)
                return
        else:
            cached_user.sessions.append(session_data)
            cached_user.store(self._cache)
