# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from flask_restful import Api

from wazo_chatd.plugin_helpers.dependencies import MessageContext
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorParseError,
    MessageIdentityRequiredError,
)
from wazo_chatd.plugins.connectors.http import ConnectorWebhookResource
from wazo_chatd.plugins.connectors.loop import DeliveryLoop
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.services import ConnectorService
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import WebhookData

if TYPE_CHECKING:
    from wazo_auth_client import Client as AuthClient

    from wazo_chatd.database.models import Room

logger = logging.getLogger(__name__)


class ConnectorRouter:
    """Main entry point for the connector subsystem.

    Owns the delivery loop, manages connector instances, handles
    capability resolution and message forwarding.  Heavy processing
    (identity lookup, delivery tracking, persistence) happens
    asynchronously in the delivery loop.
    """

    def __init__(
        self,
        config: dict[str, str | bool],
        registry: ConnectorRegistry,
        service: ConnectorService,
        auth_client: AuthClient,
    ) -> None:
        self._registry = registry
        self._service = service
        connectors_config: dict[str, Any] = dict(config.get('connectors', {}))
        delivery_config: dict[str, Any] = dict(config.get('delivery', {}))
        self._store = ConnectorStore(
            auth_client,
            registry,
            cache_ttl=float(delivery_config.get('provider_cache_ttl', 300)),
            connectors_config=connectors_config,
        )
        self._delivery_loop = DeliveryLoop(config, registry, self._store)

    def register_http_endpoints(self, api: Api) -> None:
        api.add_resource(
            ConnectorWebhookResource,
            '/connectors/incoming',
            '/connectors/incoming/<backend>',
            resource_class_args=[self],
        )

    def start(self) -> None:
        self._delivery_loop.start()

    def stop(self) -> None:
        self._delivery_loop.shutdown()

    def validate_room_creation(self, room: Room) -> None:
        self._service.validate_room_reachability(room)

    def validate_outbound(self, context: MessageContext) -> None:
        has_external = any(u.identity for u in context.room.users)
        if has_external and not context.sender_identity_uuid:
            raise MessageIdentityRequiredError()

        if context.sender_identity_uuid:
            identity = self._service.validate_identity_reachability(
                context.room,
                str(context.message.user_uuid),
                context.sender_identity_uuid,
            )
            context.resolved_sender_identity = identity

    def on_message_created(self, context: MessageContext) -> None:
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

    def send(self, context: MessageContext) -> None:
        """Create delivery metadata and notify the async delivery loop.

        For internal-only rooms (no external participants), this is a
        no-op.  Uses PostgreSQL NOTIFY to signal the async loop after
        the transaction commits, guaranteeing data visibility.
        """
        if not context.resolved_sender_identity:
            return

        self._service.create_outbound_delivery(
            context.message, context.resolved_sender_identity
        )

    def dispatch_webhook(
        self,
        data: WebhookData,
        backend: str | None = None,
    ) -> None:
        """Parse an incoming webhook and enqueue the result.

        Uses backend classes from the registry directly — inbound parsing
        is stateless (no auth config needed).  The store is only required
        for the outbound ``send()`` path.

        Raises:
            ConnectorParseError: If no connector can handle the webhook.
        """
        backends = self._registry.available_backends()
        if not backends:
            raise ConnectorParseError('No connector backends registered')

        if backend and backend in backends:
            ordered = [backend] + [b for b in backends if b != backend]
        else:
            ordered = backends

        for name in ordered:
            cls = self._registry.get_backend(name)
            if not cls.can_handle(data):
                continue
            result = cls.on_event(data)
            if result is not None:
                self._delivery_loop.enqueue_message(result)
                return

        raise ConnectorParseError('No connector matched the webhook payload')
