# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from wazo_auth_client import Client as AuthClient

from wazo_chatd.plugin_helpers.dependencies import PluginDependencies
from wazo_chatd.plugins.connectors.http import (
    ConnectorListResource,
    ConnectorWebhookResource,
    IdentityItemResource,
    IdentityListResource,
    UserMeIdentityListResource,
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
        bus_publisher = dependencies['bus_publisher']
        hooks = dependencies['hooks']
        status_aggregator = dependencies['status_aggregator']
        thread_manager = dependencies['thread_manager']
        token_changed_subscribe = dependencies['token_changed_subscribe']
        next_token_changed_subscribe = dependencies['next_token_changed_subscribe']

        auth_client = AuthClient(**config['auth'])
        token_changed_subscribe(auth_client.set_token)

        registry = ConnectorRegistry()
        registry.discover(connectors_config=config.get('connectors', {}))

        notifier = UserIdentityNotifier(bus_publisher)
        service = ConnectorService(dao, registry, notifier, auth_client)

        router = ConnectorRouter(config, registry, service, auth_client, dao)
        thread_manager.manage(router)
        next_token_changed_subscribe(router.on_auth_available)
        status_aggregator.add_provider(router.provide_status)
        hooks.register(
            'before_room_schema_validation', router.resolve_room_participants
        )
        hooks.register('before_room_creation', router.validate_room_creation)
        hooks.register('before_message_creation', router.prepare_outbound)

        api.add_resource(
            ConnectorWebhookResource,
            '/connectors/incoming',
            '/connectors/incoming/<backend>',
            resource_class_args=[router],
        )
        api.add_resource(
            ConnectorListResource,
            '/connectors',
            resource_class_args=[router],
        )
        api.add_resource(
            IdentityListResource,
            '/identities',
            resource_class_args=[service, router],
        )
        api.add_resource(
            IdentityItemResource,
            '/identities/<uuid:identity_uuid>',
            resource_class_args=[service, router],
        )
        api.add_resource(
            UserMeIdentityListResource,
            '/users/me/identities',
            resource_class_args=[service],
        )
