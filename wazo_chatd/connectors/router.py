# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from collections.abc import Mapping

from wazo_chatd.connectors.connector import Connector
from wazo_chatd.connectors.exceptions import ConnectorParseError
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import InboundMessage

if TYPE_CHECKING:
    from wazo_chatd.database.models import Room, RoomMessage

logger = logging.getLogger(__name__)


class ConnectorRouter:
    """Registry of configured connector instances.

    Handles capability resolution, message routing, delivery
    persistence, and webhook dispatch.
    """

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry
        self._instances: dict[str, Connector] = {}

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
        # TODO: implement full outbound flow
        #  1. resolve connector from room participants
        #  2. resolve sender's UserAlias
        #  3. create MessageMeta + initial DeliveryRecord (PENDING)
        #  4. build OutboundMessage
        #  5. enqueue to server process
        pass

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
            inst for inst in self._instances.values()
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

        Subclasses or monkey-patching in tests can override this.
        """
        # TODO: implement full inbound flow
        #  1. idempotency dedup via MessageMeta.extra JSONB
        #  2. resolve sender/recipient identities
        #  3. find or create room
        #  4. persist RoomMessage + MessageMeta
        #  5. publish bus event
        raise NotImplementedError('on_message not yet implemented')

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
