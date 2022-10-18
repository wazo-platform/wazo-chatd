# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import PresenceUpdatedEvent

from .schemas import UserPresenceSchema


class PresenceNotifier:
    def __init__(self, bus):
        self._bus = bus

    def updated(self, user):
        payload = UserPresenceSchema().dump(user)
        event = PresenceUpdatedEvent(payload, user.tenant_uuid)
        self._bus.publish(event)
