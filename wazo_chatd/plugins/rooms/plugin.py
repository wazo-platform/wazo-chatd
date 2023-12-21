# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from .http import (
    UserMessageListResource,
    UserRoomListResource,
    UserRoomMessageListResource,
)
from .notifier import RoomNotifier
from .services import RoomService


class Plugin:
    def load(self, dependencies):
        api = dependencies['api']
        config = dependencies['config']
        dao = dependencies['dao']
        bus_publisher = dependencies['bus_publisher']

        notifier = RoomNotifier(bus_publisher)
        service = RoomService(config['uuid'], dao, notifier)

        api.add_resource(
            UserRoomListResource, '/users/me/rooms', resource_class_args=[service]
        )
        api.add_resource(
            UserMessageListResource,
            '/users/me/rooms/messages',
            resource_class_args=[service],
        )
        api.add_resource(
            UserRoomMessageListResource,
            '/users/me/rooms/<uuid:room_uuid>/messages',
            resource_class_args=[service],
        )
