# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_bus.resources.chatd.events import (
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
        recipients = [u for u in room.users if not u.identity]

        if message.meta and message.meta.status != 'delivered':
            recipients = [
                u for u in recipients if str(u.uuid) == str(message.user_uuid)
            ]

        for user in recipients:
            event = UserRoomMessageCreatedEvent(
                message_json, room.uuid, room.tenant_uuid, user.uuid
            )
            self._bus.publish(event)
