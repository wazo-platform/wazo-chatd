# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

from wazo_chatd.connectors.connector import Connector
from wazo_chatd.connectors.exceptions import ConnectorParseError
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage, RoomParticipant
from wazo_chatd.database.helpers import session_scope

if TYPE_CHECKING:
    from wazo_chatd.database.models import Room, RoomMessage, RoomUser
    from wazo_chatd.database.queries import DAO

    from wazo_chatd.database.queries import DAO


class MessageQueue(Protocol):
    def enqueue_message(
        self,
        message: OutboundMessage | InboundMessage,
        delay: float | None = None,
    ) -> None: ...

logger = logging.getLogger(__name__)


class ConnectorRouter:
    """Routes messages between the Flask thread and the delivery loop.

    Handles capability resolution and lightweight message forwarding.
    Heavy processing (alias lookup, delivery tracking, persistence)
    happens asynchronously in the delivery loop.
    """

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry
        self._instances: dict[str, Connector] = {}
        self._queue: MessageQueue | None = None

    def set_manager(self, queue: MessageQueue) -> None:
        self._queue = queue

    def load_providers(self, dao: DAO) -> None:
        """Load connector instances from ChatProvider records.

        TODO: Replace with confd client fetch once wazo-confd-mock
        supports chat_provider responses. Currently reads directly
        from chatd's own database.
        """
        self._instances.clear()

        with session_scope():
            for provider in dao.provider.list_():
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
                    {},
                )
                self._instances[str(provider.name)] = instance
                logger.info(
                    'Loaded connector instance %r (backend=%r)',
                    provider.name,
                    backend,
                )

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
        """Extract participant data and enqueue an outbound message.

        For internal-only rooms (no external participants), this is a
        no-op.  All heavy processing (alias lookup, delivery tracking)
        happens in the worker process.
        """
        participants = self._extract_participants(room.users)
        if not any(p.identity for p in participants):
            return

        outbound = OutboundMessage(
            room_uuid=str(room.uuid),
            message_uuid=str(message.uuid),
            sender_uuid=str(message.user_uuid),
            body=str(message.content),
            participants=participants,
            metadata={'idempotency_key': str(message.uuid)},
        )

        if self._queue:
            self._queue.enqueue_message(outbound)

    @staticmethod
    def _extract_participants(
        users: list[RoomUser],
    ) -> tuple[RoomParticipant, ...]:
        return tuple(
            RoomParticipant(
                uuid=str(u.uuid),
                identity=str(u.identity) if u.identity else None,
            )
            for u in users
        )

    def dispatch_webhook(
        self,
        raw_data: Mapping[str, str],
        backend: str | None = None,
    ) -> None:
        """Parse an incoming webhook and enqueue the result for the worker.

        Uses a two-phase dispatch:

        1. ``can_handle('webhook', raw_data)`` pre-filters connectors
           cheaply (header/content-type checks).
        2. ``on_event('webhook', raw_data)`` does full parsing on
           candidates until one returns a non-None :class:`InboundMessage`.

        When *backend* is provided (from the URL path), matching instances
        are tried first as a fast path. Remaining instances are tried as
        fallback.

        Raises:
            ConnectorParseError: If no connector can handle the webhook.
        """
        instances = list(self._instances.values())
        if not instances:
            raise ConnectorParseError('No connector instances registered')

        if backend:
            hint_match = [i for i in instances if getattr(i, 'backend', None) == backend]
            rest = [i for i in instances if i not in hint_match]
            ordered = hint_match + rest
        else:
            ordered = instances

        for instance in ordered:
            if not instance.can_handle('webhook', raw_data):
                continue
            inbound = instance.on_event('webhook', raw_data)
            if inbound is not None:
                if self._queue:
                    self._queue.enqueue_message(inbound)
                return

        raise ConnectorParseError('No connector matched the webhook payload')

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
