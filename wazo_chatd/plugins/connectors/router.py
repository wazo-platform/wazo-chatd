# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from xivo.status import Status

from wazo_chatd.plugin_helpers.dependencies import ConfigDict, MessageContext
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorAuthException,
    ConnectorParseError,
    MessageIdentityRequiredException,
)
from wazo_chatd.plugins.connectors.loop import DeliveryLoop
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.services import ConnectorService
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    StatusUpdate,
    WebhookData,
)

if TYPE_CHECKING:
    from wazo_auth_client import Client as AuthClient

    from wazo_chatd.database.models import Room
    from wazo_chatd.database.queries import DAO

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
        dao: DAO,
    ) -> None:
        self._registry = registry
        self._service = service
        self._dao = dao
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
            raise MessageIdentityRequiredException()

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
            'status': Status.ok if is_running else Status.fail,
            'in_flight': loop.in_flight_count,
            'restart_count': loop.restart_count,
            'instances': len(self._store),
        }

    def resolve_room_participants(self, body: dict, tenant_uuid: str) -> None:
        self._service.resolve_room_participants(body, tenant_uuid)

    def dispatch_webhook(
        self,
        data: WebhookData,
        backend: str | None = None,
    ) -> None:
        """Parse, authenticate, and enqueue an incoming webhook.

        Parsing (``can_handle`` / ``on_event``) is stateless (classmethods).
        Signature verification requires the per-tenant instance held in
        the store: the recipient identity (or external_id for status
        updates) resolves the tenant; the store yields the instance;
        the instance verifies.

        Raises:
            ConnectorParseError: No connector handled the payload, or
                the tenant could not be resolved, or no instance is
                cached for (tenant, backend).
            ConnectorAuthException: The connector rejected the signature.
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
                self._verify_and_enqueue(data, result, backend=name)
                return

        raise ConnectorParseError('No connector matched the webhook payload')

    def _verify_and_enqueue(
        self,
        data: WebhookData,
        result: InboundMessage | StatusUpdate,
        backend: str,
    ) -> None:
        tenant_uuid = self._resolve_tenant(result, backend)
        if tenant_uuid is None:
            raise ConnectorParseError(
                f'Cannot resolve tenant for inbound {backend!r} event'
            )

        instance = self._store.find_by_backend(backend, tenant_uuid)
        if instance is None:
            raise ConnectorParseError(
                f'No connector instance cached for tenant {tenant_uuid!r} '
                f'backend {backend!r}'
            )

        if not instance.verify_signature(data):
            raise ConnectorAuthException()

        self._delivery_loop.enqueue_message(result)

    def _resolve_tenant(
        self, event: InboundMessage | StatusUpdate, backend: str
    ) -> str | None:
        match event:
            case InboundMessage(recipient=recipient):
                return self._dao.user_identity.find_tenant_by_identity(
                    recipient, backend
                )
            case StatusUpdate(external_id=external_id):
                return self._dao.room.find_tenant_by_external_id(external_id, backend)
