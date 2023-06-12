# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedChannel, CachedLine


class ChannelCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def find(self, name: str):
        try:
            return CachedChannel.load(self._cache, name)
        except ValueError:
            return None

    def update(self, channel: CachedChannel):
        channel.save(self._cache)

    def delete_all(self):
        for line in CachedLine.load_all(self._cache):
            for channel in line.channels:
                channel.delete(self._cache)
                line.channels.remove(channel)
                line.save(self._cache)
