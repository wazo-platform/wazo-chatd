# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import (
    RoomCreatedEvent,
)

from .schemas import RoomSchema


class RoomNotifier:

    def __init__(self, bus):
        self._bus = bus

    def created(self, room):
        room_json = RoomSchema().dump(room).data
        event = RoomCreatedEvent(room_json)
        self._bus.publish(event)
