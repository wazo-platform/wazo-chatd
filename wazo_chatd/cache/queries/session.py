# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedSession
from wazo_chatd.exceptions import UnknownSessionException


class SessionCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def get(self, session_uuid: str):
        try:
            return CachedSession.load(self._cache, session_uuid)
        except ValueError:
            raise UnknownSessionException(session_uuid)

    def find(self, session_uuid: str):
        try:
            return CachedSession.load(self._cache, session_uuid)
        except ValueError:
            return None

    def list_(self):
        return CachedSession.load_all(self._cache)

    def update(self, session: CachedSession):
        session.save(self._cache)
