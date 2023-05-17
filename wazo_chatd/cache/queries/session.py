# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache import get_local_cache
from wazo_chatd.cache.models import CachedSession
from wazo_chatd.database.models import Session
from wazo_chatd.exceptions import UnknownSessionException, UnknownUserException


class SessionCache:
    @property
    def users(self):
        return get_local_cache().values()

    @classmethod
    def sessions(cls, user_uuid: str):
        if user := get_local_cache().get(str(user_uuid), None):
            return user.sessions
        raise UnknownUserException(user_uuid)

    def get(self, session_uuid: str):
        session_uuid = str(session_uuid)
        for user in self.users:
            for session in user.sessions:
                if session.uuid == session_uuid:
                    return self.from_cache(session)
        else:
            raise UnknownSessionException(session_uuid)

    def find(self, session_uuid: str):
        session_uuid = str(session_uuid)
        sessions = [session for user in self.users for session in user.sessions]

        if session_uuid:
            sessions = [session for session in sessions if session.uuid == session_uuid]

        if sessions:
            return self.from_cache(sessions[0])
        return None

    def list_(self):
        return [
            self.from_cache(session) for user in self.users for session in user.sessions
        ]

    def update(self, session: Session):
        user_uuid = str(session.user_uuid)
        session_data = CachedSession.from_sql(session)

        for existing_session in self.sessions(user_uuid):
            if existing_session.uuid == str(session.uuid):
                existing_session = session_data
                return
        else:
            self.sessions(user_uuid).append(session_data)

    @staticmethod
    def from_cache(session: CachedSession) -> CachedSession:
        session.user = get_local_cache()[session.user_uuid]
        return session
