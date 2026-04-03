# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from flask_restful import Api
from sqlalchemy import text

from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.queries import DAO
from wazo_chatd.plugin_helpers.dependencies import MessageContext
from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorParseError,
    MessageAliasRequiredError,
    UnreachableParticipantError,
)
from wazo_chatd.plugins.connectors.http import (
    ConnectorReloadResource,
    ConnectorWebhookResource,
)
from wazo_chatd.plugins.connectors.loop import DeliveryLoop
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import WebhookData

if TYPE_CHECKING:
    from wazo_chatd.database.models import Room, RoomMessage, RoomUser

logger = logging.getLogger(__name__)


class ConnectorRouter:
    """Main entry point for the connector subsystem.

    Owns the delivery loop, manages connector instances, handles
    capability resolution and message forwarding. Heavy processing
    (alias lookup, delivery tracking, persistence) happens
    asynchronously in the delivery loop.
    """

    def __init__(
        self,
        config: dict[str, str | bool],
        registry: ConnectorRegistry,
        dao: DAO,
    ) -> None:
        self._registry = registry
        self._dao = dao
        self._connectors_config: dict[str, Any] = dict(config.get('connectors', {}))
        self._store = ConnectorStore()
        self._delivery_loop = DeliveryLoop(config, registry, self._store)

    def register_http_endpoints(self, api: Api) -> None:
        api.add_resource(
            ConnectorWebhookResource,
            '/connectors/incoming',
            '/connectors/incoming/<backend>',
            resource_class_args=[self],
        )
        api.add_resource(
            ConnectorReloadResource,
            '/connectors/reload',
            resource_class_args=[self],
        )

    def start(self) -> None:
        self._delivery_loop.start()

    def stop(self) -> None:
        self._delivery_loop.shutdown()

    def validate_room_creation(self, room: Room) -> None:
        for user in room.users:
            if not user.identity:
                continue
            reachable = self._registry.resolve_reachable_types(str(user.identity))
            if not reachable:
                raise UnreachableParticipantError(str(user.identity))

    def validate_outbound(self, context: MessageContext) -> None:
        has_external = any(u.identity for u in context.room.users)
        if has_external and not context.sender_alias_uuid:
            raise MessageAliasRequiredError()

    def on_room_message_created(self, context: MessageContext) -> None:
        self.send(context)

    def provide_status(self, status: dict[str, dict[str, str | int]]) -> None:
        loop = self._delivery_loop
        is_running = loop.is_running
        status['connectors'] = {
            'status': 'ok' if is_running else 'fail',
            'in_flight': loop.in_flight_count,
            'restart_count': loop.restart_count,
            'instances': len(self._store),
        }

    def load_providers(self) -> None:
        """Load connector instances from ChatProvider records.

        TODO: Replace with confd client fetch once wazo-confd-mock
        supports chat_provider responses. Currently reads directly
        from chatd's own database.
        """
        new_instances: dict[str, Connector] = {}

        with session_scope():
            for provider in self._dao.provider.list_():
                backend = str(provider.backend)
                try:
                    cls = self._registry.get_backend(backend)
                except KeyError:
                    logger.warning(
                        'Backend %r not available, skipping provider %r',
                        backend,
                        provider.name,
                    )
                    continue

                instance = cls()
                instance.configure(
                    str(provider.type_),
                    dict(provider.configuration) if provider.configuration else {},
                    self._connectors_config.get(backend, {}),
                )
                new_instances[str(provider.name)] = instance
                logger.info(
                    'Loaded connector instance %r (backend=%r)',
                    provider.name,
                    backend,
                )

        self._store.set(new_instances)

    def invalidate_cache(self) -> None:
        """Mark the connector cache as stale.

        The next operation that needs provider data will trigger a
        fresh fetch from confd.
        """
        logger.info('Connector cache invalidated')
        self._store.set({})

    def add_instance(self, name: str, connector: Connector) -> None:
        """Register a configured connector instance.

        Args:
            name: Unique name for this instance (e.g. provider name).
            connector: A configured connector instance.
        """
        self._store.register(name, connector)

    def send(self, context: MessageContext) -> None:
        """Create delivery metadata and notify the async delivery loop.

        For internal-only rooms (no external participants), this is a
        no-op.  Uses PostgreSQL NOTIFY to signal the async loop after
        the transaction commits, guaranteeing data visibility.
        """
        room, message = context.room, context.message
        has_external = any(u.identity for u in room.users)
        if not has_external:
            return

        assert context.sender_alias_uuid is not None
        meta = self._dao.room.create_pending_delivery(message)
        meta.sender_alias_uuid = context.sender_alias_uuid

        self._dao.room.session.execute(
            text("SELECT pg_notify('connector_delivery', :payload)"),
            {'payload': str(message.uuid)},
        )

    def dispatch_webhook(
        self,
        data: WebhookData,
        backend: str | None = None,
    ) -> None:
        """Parse an incoming webhook and enqueue the result.

        Uses a two-phase dispatch:

        1. ``can_handle(data)`` pre-filters connectors cheaply.
        2. ``on_event(data)`` does full parsing on candidates until one
           returns a non-None result.

        When *backend* is provided (from the URL path), matching instances
        are tried first as a fast path. Remaining instances are tried as
        fallback.

        Raises:
            ConnectorParseError: If no connector can handle the webhook.
        """
        instances = list(self._store)
        if not instances:
            raise ConnectorParseError('No connector instances registered')

        if backend:
            hint_match = [
                i for i in instances if getattr(i, 'backend', None) == backend
            ]
            rest = [i for i in instances if i not in hint_match]
            ordered = hint_match + rest
        else:
            ordered = instances

        for instance in ordered:
            if not instance.can_handle(data):
                continue
            result = instance.on_event(data)
            if result is not None:
                self._delivery_loop.enqueue_message(result)
                return

        raise ConnectorParseError('No connector matched the webhook payload')
