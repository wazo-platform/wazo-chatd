# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedChannel, CachedLine
from wazo_chatd.database.models import Channel


class ChannelCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def find(self, name: str):
        try:
            return CachedChannel.restore(self._cache, name)
        except ValueError:
            return None

    def update(self, channel: CachedChannel):
        channel.store(self._cache)

    def delete_all(self):
        pass
        # for user in self.users:
        #     for line in user.lines:
        #         line.channels.clear()
