# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ..helpers import Session
from .channel import ChannelDAO
from .endpoint import EndpointDAO
from .line import LineDAO
from .refresh_token import RefreshTokenDAO
from .room import RoomDAO
from .session import SessionDAO
from .tenant import TenantDAO
from .user import UserDAO
from .user_identity import UserIdentityDAO


class DAO:
    channel: ChannelDAO
    endpoint: EndpointDAO
    line: LineDAO
    refresh_token: RefreshTokenDAO
    room: RoomDAO
    session: SessionDAO
    tenant: TenantDAO
    user: UserDAO
    user_identity: UserIdentityDAO
    _daos = {
        'channel': ChannelDAO,
        'endpoint': EndpointDAO,
        'line': LineDAO,
        'refresh_token': RefreshTokenDAO,
        'room': RoomDAO,
        'session': SessionDAO,
        'tenant': TenantDAO,
        'user': UserDAO,
        'user_identity': UserIdentityDAO,
    }

    def __init__(self):
        for name, dao in self._daos.items():
            setattr(self, name, dao(Session))
