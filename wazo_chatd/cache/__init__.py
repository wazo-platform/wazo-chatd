# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from .client import CacheClient
from .queries.channel import ChannelCache
from .queries.endpoint import EndpointCache
from .queries.line import LineCache
from .queries.refresh_token import RefreshTokenCache
from .queries.session import SessionCache
from .queries.user import UserCache


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
