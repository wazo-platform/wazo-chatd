# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.cache import get_local_cache
from wazo_chatd.cache.models import CachedChannel, CachedLine
from wazo_chatd.database.models import Channel
from wazo_chatd.exceptions import UnknownUserException


class ChannelCache:
    @property
    def users(self):
        return get_local_cache().values()

    @property
    def channels(self):
        return [
            channel
            for user in self.users
            for line in user.lines
            for channel in line.channels
        ]

    def get_channels(self, user_uuid: str, line_id: int):
        if user := get_local_cache().get(user_uuid, None):
            for line in user.lines:
                if line.id == line_id:
                    return line.channels
        raise UnknownUserException(user_uuid)

    def find(self, name: str):
        channels = self.channels

        if name:
            channels = [channel for channel in channels if channel.name == name]

        if channels:
            return self.from_cache(channels[0])
        return None

    def update(self, channel: Channel):
        channel_data = CachedChannel.from_sql(channel)

        for user in self.users:
            for line in user.lines:
                if line.id == channel.line_id:
                    for existing_channel in line.channels:
                        if existing_channel.name == channel.name:
                            existing_channel = channel_data
                            break
                    else:
                        line.channels.append(channel_data)
                    self._update_line_states(line)
                    return

    def delete_all(self):
        for user in self.users:
            for line in user.lines:
                line.channels.clear()
                line.channels_state = []

    def _update_line_states(self, line: CachedLine):
        line.channels_state = [channel.state for channel in line.channels]

    @staticmethod
    def from_cache(channel: CachedChannel) -> CachedChannel:
        for user in get_local_cache().values():
            for line in user.lines:
                if line.id == channel.line_id:
                    line.user = user
                    channel.line = line

        return channel
