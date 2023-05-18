# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache import get_local_cache
from wazo_chatd.cache.models import CachedChannel, CachedEndpoint, CachedLine
from wazo_chatd.database.models import Channel, Endpoint, Line
from wazo_chatd.exceptions import UnknownUserException, UnknownLineException


class LineCache:
    @property
    def users(self):
        return get_local_cache().values()

    @classmethod
    def lines(cls, user_uuid: str):
        user_uuid = str(user_uuid)
        user = get_local_cache().get(user_uuid, None)
        if not user:
            raise UnknownUserException(user_uuid)
        return user.lines

    def get(self, line_id: int):
        for user in self.users:
            for line in user.lines:
                if line.id == line_id:
                    return line
        raise UnknownLineException(line_id)

    def find(self, line_id: int):
        return self.find_by(id=line_id)

    def find_by(self, **kwargs):
        lines = [line for user in self.users for line in user.lines]

        line_id = kwargs.pop('id', None)
        if line_id:
            lines = [line for line in lines if line.id == line_id]

        endpoint_name = kwargs.pop('endpoint_name', None)
        if endpoint_name:
            lines = [line for line in lines if line.endpoint_name == endpoint_name]

        if lines:
            return lines[0]
        return None

    def list_(self):
        return [line for user in self.users for line in user.lines]

    def update(self, line: Line):
        user_uuid = str(line.user_uuid)
        line_id = int(line.id)
        data = CachedLine.from_sql(line)

        for existing_line in self.lines(user_uuid):
            if existing_line.id == line_id:
                data.endpoint = existing_line.endpoint
                data.channels = existing_line.channels
                existing_line = data
                return
        else:
            self.lines(user_uuid).append(data)

    def associate_endpoint(self, line: Line, endpoint: Endpoint):
        cached_line = self.get(line.id)
        cached_line.endpoint = CachedEndpoint(name=endpoint.name, state=endpoint.state)
        cached_line.endpoint_name = endpoint.name
        cached_line.endpoint_state = endpoint.state

    def dissociate_endpoint(self, line: Line):
        cached_line = self.get(line.id)
        cached_line.endpoint = None
        cached_line.endpoint_name = None
        cached_line.endpoint_state = None

    def add_channel(self, line: CachedLine, channel: Channel):
        for cached_channel in line.channels:
            if cached_channel.name == channel.name:
                return
        cached_channel = CachedChannel.from_sql(channel)
        cached_channel.line_id = line.id
        line.channels.append(cached_channel)
        line.channels_state = [channel.state for channel in line.channels]

    def remove_channel(self, line: Line, channel: Channel):
        cached_line = self.get(line.id)
        for cached_channel in cached_line.channels:
            if cached_channel.name == channel.name:
                cached_line.channels.remove(cached_channel)
                cached_line.channels_state = [
                    channel.state for channel in cached_line.channels
                ]
                return

    @staticmethod
    def from_cache(line: CachedLine):
        user_uuid = line.user_uuid
        if user_uuid:
            line.user = get_local_cache().get(user_uuid, None)
        return line
