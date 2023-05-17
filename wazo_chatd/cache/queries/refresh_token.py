# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache import get_local_cache
from wazo_chatd.cache.models import CachedRefreshToken
from wazo_chatd.database.models import RefreshToken
from wazo_chatd.exceptions import UnknownUserException, UnknownRefreshTokenException


class RefreshTokenCache:
    @property
    def users(self):
        return get_local_cache().values()

    @classmethod
    def refresh_tokens(cls, user_uuid: str) -> list[CachedRefreshToken]:
        user_uuid = str(user_uuid)
        user = get_local_cache().get(user_uuid, None)
        if not user:
            raise UnknownUserException(user_uuid)
        return user.refresh_tokens

    def get(self, user_uuid: str, client_id: str):
        for token in self.refresh_tokens(user_uuid):
            if token.client_id == client_id:
                return self.from_cache(token)
        raise UnknownRefreshTokenException(client_id, user_uuid)

    def find(self, user_uuid: str, client_id: str):
        user_uuid = str(user_uuid)
        tokens = [token for user in self.users for token in user.refresh_tokens]

        if user_uuid:
            tokens = [token for token in tokens if token.user_uuid == user_uuid]
        if client_id:
            tokens = [token for token in tokens if token.client_id == client_id]

        if tokens:
            return tokens[0]
        return None

    def list_(self):
        return [
            self.from_cache(token) for user in self.users for token in user.refresh_tokens
        ]

    def update(self, refresh_token: RefreshToken):
        user_uuid = str(refresh_token.user_uuid)
        client_id = str(refresh_token.client_id)
        data = CachedRefreshToken.from_sql(refresh_token)

        for token in self.refresh_tokens(user_uuid):
            if token.client_id == client_id:
                token = data
                return
        else:
            self.refresh_tokens(user_uuid).append(data)

    @staticmethod
    def from_cache(refresh_token: CachedRefreshToken) -> CachedRefreshToken:
        refresh_token.user = get_local_cache()[refresh_token.user_uuid]
        return refresh_token
