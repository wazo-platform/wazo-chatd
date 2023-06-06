# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedChannel, CachedEndpoint, CachedLine
from wazo_chatd.database.models import Channel, Line
from wazo_chatd.exceptions import UnknownLineException


class LineCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def get(self, line_id: int):
        try:
            return CachedLine.restore(self._cache, line_id)
        except ValueError:
            raise UnknownLineException(line_id)

    def find(self, line_id: int):
        try:
            return CachedLine.restore(self._cache, line_id)
        except ValueError:
            return None

    def find_by(self, **kwargs):
        lines = CachedLine.all(self._cache)

        if line_id := kwargs.get('id', None):
            lines = [line for line in lines if line.id == line_id]

        if endpoint_name := kwargs.get('endpoint_name', None):
            lines = [line for line in lines if line.endpoint_name == endpoint_name]

        return lines[0] if lines else None

    def list_(self):
        return CachedLine.all(self._cache)

    def update(self, line: Line):
        previous_line = CachedLine.restore(self._cache, line.id)
        updated_line = CachedLine.from_sql(line)

        updated_line.endpoint = previous_line.endpoint
        updated_line.endpoint_name = previous_line.endpoint_name
        updated_line.channels = previous_line.channels
        updated_line.store(self._cache)

    def associate_endpoint(self, line: Line, endpoint: CachedEndpoint):
        endpoint.line_id = int(line.id)
        cached_line = CachedLine.restore(self._cache, line.id)
        cached_line.endpoint = endpoint
        cached_line.endpoint_name = endpoint.name
        cached_line.store(self._cache)

    def dissociate_endpoint(self, line: Line):
        cached_line = CachedLine.restore(self._cache, line.id)
        if cached_line.endpoint:
            cached_line.endpoint.line_id = None
            cached_line.endpoint = None
            cached_line.endpoint_name = None
            cached_line.store(self._cache)

    def add_channel(self, line: CachedLine, channel: Channel):
        for existing_channel in line.channels:
            if existing_channel.name == channel.name:
                return

        cached_channel = CachedChannel.from_sql(channel)
        cached_channel.line_id = int(line.id)
        line.channels.append(cached_channel)
        line.store(self._cache)

    def remove_channel(self, line: CachedLine, channel: CachedChannel):
        for existing_channel in line.channels:
            if existing_channel.name == channel.name:
                existing_channel.remove(self._cache)
                line.channels.remove(existing_channel)
                line.store(self._cache)
                return
