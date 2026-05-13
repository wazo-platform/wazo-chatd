# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from xivo.status import Status

from wazo_chatd.plugin_helpers.dependencies import ConfigDict, MessageContext
from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    BackendNotConfiguredException,
    ConnectorAuthException,
    ConnectorParseError,
    ConnectorTransientError,
    InventoryNotSupportedException,
    MessageIdentityRequiredException,
    NoSuchConnectorException,
    UnknownBackendException,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.runner import (
    DeliveryRunner,
    ListenerRunner,
    NullRunner,
)
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

    _delivery_runner: DeliveryRunner | NullRunner
    _listener_runner: ListenerRunner | NullRunner

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
        if not registry.available_backends():
            logger.info('No connector backends registered; skipping runner startup')
            self._delivery_runner = self._listener_runner = NullRunner()
            return

        self._delivery_runner = DeliveryRunner(config, registry, self._store)
        self._listener_runner = ListenerRunner(
            config, self._store, self._delivery_runner.enqueue_message
        )

    def on_auth_available(self, _token: str) -> None:
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

    def list_connectors(self, tenant_uuid: str) -> list[dict[str, object]]:
        backends = self._registry.available_backends()
        uncached = [
            (tenant_uuid, name)
            for name in backends
            if self._store.peek(name, tenant_uuid) is None
        ]
        if uncached:
            self._store.batch_find(uncached)

        result: list[dict[str, object]] = []
        for name in backends:
            cls = self._registry.get_backend(name)
            configured = self._store.peek(name, tenant_uuid) is not None
            result.append(
                {
                    'name': name,
                    'supported_types': list(cls.supported_types),
                    'configured': configured,
                }
            )

        return result

    def list_connector_inventory(
        self, tenant_uuid: str, backend: str
    ) -> list[dict[str, object]]:
        if backend not in self._registry.available_backends():
            raise NoSuchConnectorException(backend)

        connector = self._store.get(backend, tenant_uuid)

        try:
            provider_identities = connector.list_provider_identities()
        except NotImplementedError:
            raise InventoryNotSupportedException(backend) from None

        existing = self._dao.user_identity.list_(
            tenant_uuids=[tenant_uuid], backends=[backend]
        )
        bindings = {str(u.identity): u for u in existing}

        result: list[dict[str, object]] = []
        for pi in provider_identities:
            bound = bindings.get(pi.identity)
            result.append(
                {
                    'identity': pi.identity,
                    'type_': pi.type,
                    'binding': (
                        {'uuid': str(bound.uuid), 'user_uuid': str(bound.user_uuid)}
                        if bound
                        else None
                    ),
                }
            )

        return result

    def invalidate_backend_cache(self, tenant_uuid: str, backend: str) -> None:
        """Drop a cached connector instance and resync runners."""
        if self._store.peek(backend, tenant_uuid) is not None:
            self._store.drop(backend, tenant_uuid)

        self._delivery_runner.resync_pollers()
        self._listener_runner.resync()

    def validate_tenant_backend(self, tenant_uuid: str, backend: str) -> None:
        """Validate a backend is usable for a tenant; caches on success.

        Raises:
          - :class:`UnknownBackendException` (400) — backend not registered.
          - :class:`BackendNotConfiguredException` (400) — no tenant config.
          - :class:`AuthServiceUnavailableException` (503) — auth transient error.
        """
        self._store.get(backend, tenant_uuid)

    def reconcile_after_create(self) -> None:
        """Resync runners after a UserIdentity create.

        Cache warming is handled by :meth:`validate_tenant_backend`
        before insertion, so no store lookup is needed here.
        """
        self._delivery_runner.resync_pollers()
        self._listener_runner.resync()

    def reconcile_after_delete(self, tenant_uuid: str, backend: str) -> None:
        """Drop cached instance if last identity removed, then resync runners."""
        has_any = self._dao.user_identity.has_identities_for_backend(
            tenant_uuid, backend
        )
        if not has_any and self._store.peek(backend, tenant_uuid) is not None:
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
            self._service.prepare_outbound_delivery(
                context.room, context.message, identity
            )

    def provide_status(self, status: dict[str, dict[str, str | int]]) -> None:
        delivery = self._delivery_runner
        listener = self._listener_runner
        both_running = delivery.is_running and listener.is_running
        status['connectors'] = {
            'status': Status.ok if both_running else Status.fail,
            'backends_registered': len(self._registry.available_backends()),
            'in_flight': delivery.in_flight_count,
            'delivery_restart_count': delivery.restart_count,
            'listener_restart_count': listener.restart_count,
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

        if backend is not None:
            if backend not in backends:
                raise ConnectorParseError(f'Unknown connector backend {backend!r}')
            candidates = [backend]
        else:
            candidates = backends

        for name in candidates:
            cls = self._registry.get_backend(name)
            try:
                if not cls.can_handle(data):
                    continue
                result = cls.on_event(data)
            except Exception:
                logger.exception(
                    'Backend %r raised during webhook dispatch; skipping',
                    name,
                )
                continue
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

        try:
            instance = self._store.get(backend, tenant_uuid)
        except (UnknownBackendException, BackendNotConfiguredException) as exc:
            raise ConnectorParseError(
                f'No connector instance for tenant {tenant_uuid!r} '
                f'backend {backend!r}'
            ) from exc
        except AuthServiceUnavailableException as exc:
            raise ConnectorTransientError(
                f'Auth service unavailable while resolving connector for '
                f'tenant {tenant_uuid!r} backend {backend!r}'
            ) from exc

        if instance.verifies_signatures:
            try:
                valid = instance.verify_signature(data)
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
            case _:
                raise TypeError(f'Unexpected event type: {type(event).__name__}')
