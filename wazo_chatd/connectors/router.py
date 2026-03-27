# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from wazo_chatd.connectors.connector import Connector
from wazo_chatd.connectors.delivery import DeliveryStatus
from wazo_chatd.connectors.exceptions import ConnectorParseError, NoCommonConnectorError
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage
from wazo_chatd.database.models import DeliveryRecord, MessageMeta
from wazo_chatd.database.models import RoomMessage as RoomMessageModel
from wazo_chatd.plugins.rooms.notifier import RoomNotifier

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as SASession

    from wazo_chatd.database.models import Room, RoomMessage, UserAlias

logger = logging.getLogger(__name__)


class ConnectorRouter:
    """Registry of configured connector instances.

    Handles capability resolution, message routing, delivery
    persistence, and webhook dispatch.
    """

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry
        self._instances: dict[str, Connector] = {}
        self._session: SASession | None = None
        self._enqueue: Callable[[OutboundMessage], None] | None = None
        self._alias_resolver: Callable[[str, str], UserAlias | None] | None = None
        self._notifier: RoomNotifier | None = None
        self._room_resolver: Callable[[str, str, str], Room] | None = None
        self._dedup_checker: Callable[[str], bool] | None = None

    def set_session(self, session: SASession) -> None:
        """Set the DB session for delivery persistence."""
        self._session = session

    def set_enqueue(self, enqueue: Callable[[OutboundMessage], None]) -> None:
        """Set the callback for enqueuing outbound messages to the server process."""
        self._enqueue = enqueue

    def set_alias_resolver(
        self,
        resolver: Callable[[str, str], UserAlias | None],
    ) -> None:
        """Set the function that resolves a user's alias for a given type.

        Args:
            resolver: Callable(user_uuid, type_) -> UserAlias | None
        """
        self._alias_resolver = resolver

    def set_notifier(self, notifier: RoomNotifier) -> None:
        """Set the notifier for publishing bus events on message creation."""
        self._notifier = notifier

    def set_room_resolver(
        self,
        resolver: Callable[[str, str, str], Room],
    ) -> None:
        """Set the function that finds or creates a room for identities.

        Args:
            resolver: Callable(tenant_uuid, sender_identity, recipient_identity) -> Room
        """
        self._room_resolver = resolver

    def set_dedup_checker(
        self,
        checker: Callable[[str], bool],
    ) -> None:
        """Set the function that checks if an idempotency key already exists.

        Args:
            checker: Callable(idempotency_key) -> True if duplicate
        """
        self._dedup_checker = checker

    def sync_to_server(self) -> None:
        """Serialize provider configs and send through pipe to server process.

        Called after load_from_cache or after a restart.
        """
        # TODO: implement pipe sync when server process is wired
        pass

    def invalidate_cache(self) -> None:
        """Mark the connector cache as stale.

        The next operation that needs provider data will trigger a
        fresh fetch from confd.
        """
        logger.info('Connector cache invalidated')
        self._instances.clear()

    def add_instance(self, name: str, connector: Connector) -> None:
        """Register a configured connector instance.

        Args:
            name: Unique name for this instance (e.g. provider name).
            connector: A configured connector instance.
        """
        self._instances[name] = connector

    def list_capabilities(self, room: Room) -> set[str]:
        """Compute common connector types for the room participants.

        For rooms with only internal Wazo users, returns ``{"internal"}``.
        For rooms with external participants, determines reachable types
        by calling :meth:`~Connector.normalize_identity` on each
        registered connector.  ``"internal"`` is excluded when any
        external participant is present.
        """
        external_users = [u for u in room.users if u.identity is not None]

        if not external_users:
            return {'internal'}

        reachable_types: set[str] = set()
        for external_user in external_users:
            user_types = self._resolve_reachable_types(external_user.identity)
            if not reachable_types:
                reachable_types = user_types
            else:
                reachable_types &= user_types

        return reachable_types

    def send(self, room: Room, message: RoomMessage) -> None:
        """Route an outbound message through the appropriate connector.

        Validates capabilities, resolves the sender's UserAlias,
        persists a MessageMeta with PENDING status, and enqueues the
        OutboundMessage to the server process.

        For internal-only rooms (no external participants), this is a
        no-op.
        """
        capabilities = self.list_capabilities(room)
        if not capabilities:
            raise NoCommonConnectorError(
                'Room participants share no common connector type'
            )

        # Internal-only rooms don't need external delivery
        if capabilities == {'internal'}:
            return

        external_users = [u for u in room.users if u.identity is not None]
        if not external_users:
            return

        chosen_type = next(iter(capabilities))
        recipient_identity = str(external_users[0].identity)

        sender_alias_str = ''
        backend_name = chosen_type
        if self._alias_resolver:
            alias = self._alias_resolver(str(message.user_uuid), chosen_type)
            if alias:
                sender_alias_str = str(alias.identity)
                if alias.provider:
                    backend_name = str(alias.provider.backend)

        meta = MessageMeta(
            message_uuid=message.uuid,
            type_=chosen_type,
            backend=backend_name,
            extra={'outbound_idempotency_key': str(message.uuid)},
        )
        initial_record = DeliveryRecord(
            message_uuid=message.uuid,
            status=DeliveryStatus.PENDING.value,
        )

        if self._session:
            self._session.add(meta)
            self._session.add(initial_record)
            self._session.flush()

        outbound = OutboundMessage(
            sender_alias=sender_alias_str,
            recipient_alias=recipient_identity or '',
            sender_uuid=str(message.user_uuid),
            body=str(message.content),
            delivery_uuid=str(message.uuid),
            metadata={'idempotency_key': str(message.uuid)},
        )

        if self._enqueue:
            self._enqueue(outbound)

    def dispatch_webhook(
        self,
        backend: str,
        raw_data: Mapping[str, str],
    ) -> None:
        """Dispatch an incoming webhook to the matching connector.

        Finds all connector instances whose backend matches, calls
        :meth:`~Connector.on_event` with ``'webhook'`` on each until
        one returns a non-None :class:`InboundMessage`, then forwards
        it to :meth:`on_message`.

        Args:
            backend: The backend name from the URL path
                (e.g. ``"twilio"`` from ``/connectors/incoming/twilio``).
            raw_data: Plain dict extracted from the HTTP request body.

        Raises:
            ConnectorParseError: If no connector instance matches the
                backend or none produces a message.
        """
        matching = [
            inst
            for inst in self._instances.values()
            if getattr(inst, 'backend', None) == backend
        ]
        if not matching:
            raise ConnectorParseError(
                f'No connector instance registered for backend {backend!r}'
            )

        for instance in matching:
            inbound = instance.on_event('webhook', raw_data)
            if inbound is not None:
                self.on_message(inbound)
                return

    def on_message(self, inbound: InboundMessage) -> None:
        """Handle an inbound message from a connector.

        This is the convergence point for all inbound paths (webhook,
        poll, websocket).  Performs idempotency dedup, identity
        resolution, room find/create, message persistence, and bus
        notification.
        """
        idempotency_key = inbound.metadata.get('idempotency_key')
        if idempotency_key and self._dedup_checker:
            if self._dedup_checker(idempotency_key):
                logger.info(
                    'Duplicate inbound message skipped (key=%s)',
                    idempotency_key,
                )
                return

        if not self._room_resolver:
            logger.error('No room resolver configured, dropping inbound message')
            return

        room = self._room_resolver('', inbound.sender, inbound.recipient)

        message = RoomMessageModel(
            content=inbound.body,
            room_uuid=room.uuid,
            user_uuid=room.users[0].uuid if room.users else None,
            tenant_uuid=room.tenant_uuid if hasattr(room, 'tenant_uuid') else None,
            wazo_uuid=room.users[0].wazo_uuid if room.users else None,
        )

        meta = MessageMeta(
            message_uuid=message.uuid,
            backend=inbound.backend,
            extra={
                'idempotency_key': idempotency_key,
                'external_id': inbound.external_id,
            }
            if idempotency_key
            else {
                'external_id': inbound.external_id,
            },
        )
        message.meta = meta

        record = DeliveryRecord(
            message_uuid=message.uuid,
            status=DeliveryStatus.DELIVERED.value,
        )

        if self._session:
            self._session.add(message)
            self._session.add(record)
            self._session.flush()

        if self._notifier:
            self._notifier.message_created(room, message)

    def _resolve_reachable_types(self, identity: str) -> set[str]:
        """Ask each registered connector backend if it can normalize
        the given identity.  Returns the set of connector types that
        can reach this identity.
        """
        reachable: set[str] = set()
        for backend_name in self._registry.available_backends():
            cls = self._registry.get_backend(backend_name)
            instance = cls()
            try:
                instance.normalize_identity(identity)
            except (ValueError, TypeError):
                continue
            reachable.update(cls.supported_types)
        return reachable
