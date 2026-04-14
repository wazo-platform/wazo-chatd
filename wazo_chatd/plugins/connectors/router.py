# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from wazo_chatd.plugin_helpers.dependencies import ConfigDict, MessageContext
from wazo_chatd.plugin_helpers.identity import derive_external_user_uuid
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorParseError,
    MessageIdentityRequiredError,
)
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
        config: ConfigDict,
        registry: ConnectorRegistry,
        service: ConnectorService,
        auth_client: AuthClient,
    ) -> None:
        self._registry = registry
        self._service = service
        connectors_config = config.get('connectors') or {}
        delivery_config = config.get('delivery') or {}
        self._store = ConnectorStore(
            auth_client,
            registry,
            cache_ttl=float(delivery_config.get('provider_cache_ttl', 300)),
            connectors_config=connectors_config,
        )
        self._delivery_loop = DeliveryLoop(config, registry, self._store)

    def on_token_acquired(self, token: str) -> None:
        self._delivery_loop.on_token_acquired(token)

    def start(self) -> None:
        self._delivery_loop.start()

    def stop(self) -> None:
        self._delivery_loop.shutdown()

    def validate_room_creation(self, room: Room) -> None:
        self._service.validate_room_reachability(room)

    def prepare_outbound(self, context: MessageContext) -> None:
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
            self._service.prepare_outbound_delivery(context.message, identity)

    def provide_status(self, status: dict[str, dict[str, str | int]]) -> None:
        loop = self._delivery_loop
        is_running = loop.is_running
        status['connectors'] = {
            'status': 'ok' if is_running else 'fail',
            'in_flight': loop.in_flight_count,
            'restart_count': loop.restart_count,
            'instances': len(self._store),
        }

    def resolve_room_participants(self, body: dict, tenant_uuid: str) -> None:
        users = body.get('users', [])
        identities = {
            u['identity'] for u in users if u.get('identity') and not u.get('uuid')
        }
        if not identities:
            return

        resolved = self._service.resolve_users_by_identities(identities)

        for user in users:
            if user.get('uuid') or not user.get('identity'):
                continue
            identity = user['identity']
            wazo_user = resolved.get(identity)
            if wazo_user:
                user['uuid'] = str(wazo_user.uuid)
                user.pop('identity', None)
            else:
                user['uuid'] = str(derive_external_user_uuid(tenant_uuid, identity))

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
