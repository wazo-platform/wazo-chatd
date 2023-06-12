# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from .channel import ChannelCache
from .endpoint import EndpointCache
from .line import LineCache
from .refresh_token import RefreshTokenCache
from .session import SessionCache
from .user import UserCache

from wazo_chatd.cache.client import CacheClient


class CacheDAO:
    channel: ChannelCache
    endpoint: EndpointCache
    line: LineCache
    refresh_token: RefreshTokenCache
    session: SessionCache
    user: UserCache

    def __init__(self, client: CacheClient):
        self.channel = ChannelCache(client)
        self.endpoint = EndpointCache(client)
        self.line = LineCache(client)
        self.refresh_token = RefreshTokenCache(client)
        self.session = SessionCache(client)
        self.user = UserCache(client)
