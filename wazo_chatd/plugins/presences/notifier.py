# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import (
    PresenceUpdatedEvent,
)

from .schemas import UserPresenceSchema


class PresenceNotifier:

    def __init__(self, bus):
        self._bus = bus

    def updated(self, user):
        user_json = UserPresenceSchema().dump(user).data
        event = PresenceUpdatedEvent(user_json)
        self._bus.publish(event)
