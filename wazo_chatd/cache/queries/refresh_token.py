# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedRefreshToken, CachedUser
from wazo_chatd.database.models import RefreshToken
from wazo_chatd.exceptions import UnknownRefreshTokenException


class RefreshTokenCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def get(self, user_uuid: str, client_id: str):
        pkey = ':'.join([user_uuid, client_id])
        try:
            return CachedRefreshToken.restore(self._cache, pkey)
        except ValueError:
            raise UnknownRefreshTokenException(client_id, user_uuid)

    def find(self, user_uuid: str, client_id: str):
        tokens = CachedRefreshToken.pk_all(self._cache)

        if user_uuid:
            tokens &= CachedRefreshToken.pk_matches(self._cache, user_uuid)

        if client_id:
            tokens &= CachedRefreshToken.pk_matches(self._cache, client_id)

        try:
            return CachedRefreshToken.restore(self._cache, tokens.pop())
        except KeyError:
            return None

    def list_(self):
        return CachedRefreshToken.all(self._cache)

    def update(self, refresh_token: RefreshToken):
        user_uuid = str(refresh_token.user_uuid)
        client_id = str(refresh_token.client_id)
        data = CachedRefreshToken.from_sql(refresh_token)
        cached_user = CachedUser.restore(self._cache, user_uuid)

        for token in cached_user.refresh_tokens:
            if token.client_id == client_id:
                token = data
                cached_user.store(self._cache)
                return
        else:
            cached_user.refresh_tokens.append(data)
            cached_user.store(self._cache)
