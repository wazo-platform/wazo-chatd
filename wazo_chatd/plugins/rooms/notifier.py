# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import (
    UserRoomCreatedEvent,
    UserRoomMessageCreatedEvent,
)

from .schemas import MessageSchema, RoomSchema


class RoomNotifier:
    def __init__(self, bus):
        self._bus = bus

    def created(self, room):
        room_json = RoomSchema().dump(room)
        for user in room_json['users']:
            event = UserRoomCreatedEvent(room_json, room.tenant_uuid, user['uuid'])
            self._bus.publish(event)

    def message_created(self, room, message):
        message_json = MessageSchema().dump(message)
        for user in room.users:
            event = UserRoomMessageCreatedEvent(
                message_json, room.uuid, room.tenant_uuid, user.uuid
            )
            self._bus.publish(event)
