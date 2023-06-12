# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedRefreshToken
from wazo_chatd.exceptions import UnknownRefreshTokenException


class RefreshTokenCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def get(self, user_uuid: str, client_id: str):
        pk = ':'.join([user_uuid, client_id])
        try:
            return CachedRefreshToken.load(self._cache, pk)
        except ValueError:
            raise UnknownRefreshTokenException(client_id, user_uuid)

    def find(self, user_uuid: str, client_id: str):
        tokens = CachedRefreshToken.pk_all(self._cache)

        if user_uuid:
            tokens &= CachedRefreshToken.pk_matches(self._cache, user_uuid)

        if client_id:
            tokens &= CachedRefreshToken.pk_matches(self._cache, client_id)

        try:
            return CachedRefreshToken.load(self._cache, tokens.pop())
        except KeyError:
            return None

    def list_(self):
        return CachedRefreshToken.load_all(self._cache)

    def update(self, refresh_token: CachedRefreshToken):
        refresh_token.save(self._cache)
