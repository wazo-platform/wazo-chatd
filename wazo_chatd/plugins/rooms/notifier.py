# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import UserRoomCreatedEvent, UserRoomMessageCreatedEvent

from .schemas import RoomSchema, MessageSchema


class RoomNotifier:

    def __init__(self, bus):
        self._bus = bus

    def created(self, room):
        room_json = RoomSchema().dump(room).data
        for user in room_json['users']:
            event = UserRoomCreatedEvent(user['uuid'], room_json)
            self._bus.publish(event)

    def message_created(self, room, message):
        message_json = MessageSchema().dump(message).data
        message_json['room'] = {'uuid': room.uuid}
        for user in room.users:
            event = UserRoomMessageCreatedEvent(user.uuid, room.uuid, message_json)
            self._bus.publish(event)
