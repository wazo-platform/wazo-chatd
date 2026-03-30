# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.connectors.http import ConnectorWebhookResource

from .http import (
    UserAliasListResource,
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

        connector_router = dependencies.get('connector_router')

        notifier = RoomNotifier(bus_publisher)
        service = RoomService(config['uuid'], dao, notifier, connector_router)

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
        api.add_resource(
            UserAliasListResource,
            '/users/me/aliases',
            resource_class_args=[dao],
        )

        if connector_router:
            api.add_resource(
                ConnectorWebhookResource,
                '/connectors/incoming',
                '/connectors/incoming/<backend>',
                resource_class_args=[connector_router],
            )
