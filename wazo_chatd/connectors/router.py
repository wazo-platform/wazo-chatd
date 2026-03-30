# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from wazo_chatd.connectors.connector import Connector
from wazo_chatd.connectors.exceptions import ConnectorParseError
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import OutboundMessage, RoomParticipant

if TYPE_CHECKING:
    from wazo_chatd.connectors.manager import DeliveryManager
    from wazo_chatd.database.models import Room, RoomMessage, RoomUser

logger = logging.getLogger(__name__)


class ConnectorRouter:
    """Routes messages between the Flask process and the async worker.

    Handles capability resolution and lightweight message forwarding.
    Heavy processing (alias lookup, delivery tracking, persistence)
    happens in the worker process.
    """

    def __init__(self, registry: ConnectorRegistry) -> None:
        self._registry = registry
        self._instances: dict[str, Connector] = {}
        self._manager: DeliveryManager | None = None

    def set_manager(self, manager: DeliveryManager) -> None:
        self._manager = manager

    def sync_to_server(self) -> None:
        """Send current provider configs to the server process.

        If no providers are cached, sends an empty list so the worker
        doesn't block waiting for initial config.
        """
        if not self._manager:
            return
        self._manager.sync_config([])

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

        if self._manager:
            self._manager.send_message(outbound)

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
        backend: str,
        raw_data: Mapping[str, str],
    ) -> None:
        """Parse an incoming webhook and enqueue the result for the worker.

        Finds all connector instances whose backend matches, calls
        ``on_event('webhook', ...)`` on each until one returns a
        non-None :class:`InboundMessage`, then enqueues it.

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
                if self._manager:
                    self._manager.send_inbound(inbound)
                return

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
