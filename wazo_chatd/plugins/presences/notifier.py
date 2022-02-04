# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_bus.resources.chatd.events import PresenceUpdatedEvent

from .schemas import UserPresenceSchema


class PresenceNotifier:
    def __init__(self, bus):
        self._bus = bus

    def updated(self, user):
        headers = {}
        user_json = UserPresenceSchema().dump(user)
        event = PresenceUpdatedEvent(user_json)
        headers['tenant_uuid'] = user_json['tenant_uuid']
        self._bus.publish(event, headers=headers)
