# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from xivo.status import Status

from wazo_chatd.plugin_helpers.dependencies import ConfigDict, MessageContext
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorAuthException,
    ConnectorParseError,
    MessageIdentityRequiredException,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.runner import DeliveryRunner, ListenerRunner
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
        self._delivery_runner = DeliveryRunner(config, registry, self._store)
        self._listener_runner = ListenerRunner(
            config, self._store, self._delivery_runner.enqueue_message
        )

    def on_auth_available(self, token: str) -> None:
        if self._store.is_populated:
            return

        threading.Thread(
            target=self._populate_store,
            daemon=True,
            name='connector-router-populate',
        ).start()

    def _populate_store(self) -> None:
        try:
            tenant_backends = self._dao.user_identity.list_tenant_backends()
            self._store.populate(tenant_backends)
        except Exception:
            logger.exception('Failed to populate connector store')

    def probe_backend(self, tenant_uuid: str, backend: str) -> None:
        """Validate a backend is usable for a tenant; caches on success.

        Raises:
          - :class:`UnknownBackendException` (400) — backend not registered.
          - :class:`BackendNotConfiguredException` (400) — no tenant config.
          - :class:`AuthServiceUnavailableException` (503) — auth transient error.
        """
        self._store.fetch(backend, tenant_uuid)

    def reconcile_tenant_backend(self, tenant_uuid: str, backend: str) -> None:
        """Reconcile store + runners with current identity state.

        Called after a UserIdentity create or delete. Loads the
        connector instance when an identity exists and the store is
        cold; drops the instance when no identity remains and the
        store still has it. Always resyncs pollers and listeners.
        """
        has_any = self._dao.user_identity.has_identities_for_backend(
            tenant_uuid, backend
        )
        in_store = self._store.find_by_backend(backend, tenant_uuid) is not None

        if has_any and not in_store:
            self._store.load(backend, tenant_uuid)
        elif not has_any and in_store:
            self._store.drop(backend, tenant_uuid)

        self._delivery_runner.resync_pollers()
        self._listener_runner.resync()

    def start(self) -> None:
        self._delivery_runner.start()
        self._listener_runner.start()

    def stop(self) -> None:
        self._listener_runner.shutdown()
        self._delivery_runner.shutdown()

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
        loop = self._delivery_runner
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

        if backend and backend not in backends:
            logger.warning(
                'Webhook backend hint %r is not registered; '
                'falling back to full registry scan',
                backend,
            )
            backend = None

        if backend:
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

        instance = self._store.load(backend, tenant_uuid)
        if instance is None:
            raise ConnectorParseError(
                f'No connector instance for tenant {tenant_uuid!r} '
                f'backend {backend!r}'
            )

        verify = getattr(instance, 'verify_signature', None)
        if verify is not None:
            try:
                valid = verify(data)
            except Exception:
                logger.exception(
                    'verify_signature raised for backend %r tenant %s',
                    backend,
                    tenant_uuid,
                )
                valid = False
            if not valid:
                raise ConnectorAuthException()

        self._delivery_runner.enqueue_message(result)

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
