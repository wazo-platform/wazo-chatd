# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from .room import AsyncRoomDAO
from .user_identity import AsyncUserIdentityDAO


class AsyncDAO:
    room: AsyncRoomDAO
    user_identity: AsyncUserIdentityDAO

    def __init__(self) -> None:
        self.room = AsyncRoomDAO()
        self.user_identity = AsyncUserIdentityDAO()
