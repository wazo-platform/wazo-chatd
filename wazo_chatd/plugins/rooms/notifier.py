# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import UserRoomCreatedEvent

from .schemas import RoomSchema


class RoomNotifier:

    def __init__(self, bus):
        self._bus = bus

    def created(self, room):
        room_json = RoomSchema().dump(room).data
        for user in room_json['users']:
            event = UserRoomCreatedEvent(user['uuid'], room_json)
            self._bus.publish(event)

    def message_created(self, room, message):
        # TODO send message on each user
        pass
