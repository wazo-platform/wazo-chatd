# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from wazo_chatd.plugin_helpers.dependencies import PluginDependencies
from wazo_chatd.plugins.connectors.bus_consume import ConnectorBusEventHandler
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class Plugin:
    def load(self, dependencies: PluginDependencies) -> None:
        config = dependencies['config']
        api = dependencies['api']
        dao = dependencies['dao']
        bus_consumer = dependencies['bus_consumer']
        pubsub = dependencies['pubsub']
        status_aggregator = dependencies['status_aggregator']
        thread_manager = dependencies['thread_manager']

        registry = ConnectorRegistry()
        registry.discover(connectors_config=config.get('connectors', {}))

        router = ConnectorRouter(config, registry, dao)
        router.register_http_endpoints(api)

        pubsub.subscribe('room_message_created', router.on_room_message_created)

        bus_handler = ConnectorBusEventHandler(bus_consumer, router)
        bus_handler.subscribe()

        thread_manager.manage(router)
        status_aggregator.add_provider(router.provide_status)
