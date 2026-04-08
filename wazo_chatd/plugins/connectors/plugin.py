# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from wazo_auth_client import Client as AuthClient

from wazo_chatd.plugin_helpers.dependencies import PluginDependencies
from wazo_chatd.plugins.connectors.bus_consume import ConnectorBusEventHandler
from wazo_chatd.plugins.connectors.http import (
    RoomIdentityListResource,
    UserIdentityItemResource,
    UserIdentityListResource,
)
from wazo_chatd.plugins.connectors.notifier import UserIdentityNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.router import ConnectorRouter
from wazo_chatd.plugins.connectors.services import ConnectorService

logger = logging.getLogger(__name__)


class Plugin:
    def load(self, dependencies: PluginDependencies) -> None:
        config = dependencies['config']
        api = dependencies['api']
        dao = dependencies['dao']
        bus_consumer = dependencies['bus_consumer']
        bus_publisher = dependencies['bus_publisher']
        hooks = dependencies['hooks']
        status_aggregator = dependencies['status_aggregator']
        thread_manager = dependencies['thread_manager']

        registry = ConnectorRegistry()
        registry.discover(connectors_config=config.get('connectors', {}))

        auth_client = AuthClient(**config['auth'])
        token_changed_subscribe = dependencies['token_changed_subscribe']
        token_changed_subscribe(auth_client.set_token)

        notifier = UserIdentityNotifier(bus_publisher)
        service = ConnectorService(dao, registry, notifier=notifier)

        router = ConnectorRouter(config, registry, service, auth_client)
        router.register_http_endpoints(api)

        hooks.register('before_room_creation', router.validate_room_creation)
        hooks.register('before_message_creation', router.prepare_outbound)

        bus_handler = ConnectorBusEventHandler(bus_consumer, router)
        bus_handler.subscribe()

        api.add_resource(
            UserIdentityListResource,
            '/users/<uuid:user_uuid>/identities',
            resource_class_args=[service],
        )
        api.add_resource(
            UserIdentityItemResource,
            '/users/<uuid:user_uuid>/identities/<uuid:identity_uuid>',
            resource_class_args=[service],
        )

        api.add_resource(
            RoomIdentityListResource,
            '/users/me/rooms/<uuid:room_uuid>/identities',
            resource_class_args=[service],
        )

        thread_manager.manage(router)
        status_aggregator.add_provider(router.provide_status)
