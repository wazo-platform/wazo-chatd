# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ..helpers import Session
from .channel import ChannelDAO
from .endpoint import EndpointDAO
from .line import LineDAO
from .provider import ProviderDAO
from .refresh_token import RefreshTokenDAO
from .room import RoomDAO
from .session import SessionDAO
from .tenant import TenantDAO
from .user import UserDAO
from .user_alias import UserAliasDAO


class DAO:
    channel: ChannelDAO
    endpoint: EndpointDAO
    line: LineDAO
    provider: ProviderDAO
    refresh_token: RefreshTokenDAO
    room: RoomDAO
    session: SessionDAO
    tenant: TenantDAO
    user: UserDAO
    user_alias: UserAliasDAO
    _daos = {
        'channel': ChannelDAO,
        'endpoint': EndpointDAO,
        'line': LineDAO,
        'provider': ProviderDAO,
        'refresh_token': RefreshTokenDAO,
        'room': RoomDAO,
        'session': SessionDAO,
        'tenant': TenantDAO,
        'user': UserDAO,
        'user_alias': UserAliasDAO,
    }

    def __init__(self):
        for name, dao in self._daos.items():
            setattr(self, name, dao(Session))
