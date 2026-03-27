# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bus event handlers for connector configuration changes.

Subscribes to confd events (chat_provider and user_alias CRUD) and
invalidates the :class:`ConnectorRouter` cache so connector instances
are rebuilt from fresh data on next access.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wazo_chatd.bus import BusConsumer
    from wazo_chatd.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class ConnectorBusEventHandler:
    """Handles bus events related to connector configuration."""

    def __init__(self, bus_consumer: BusConsumer, router: ConnectorRouter) -> None:
        self._bus_consumer = bus_consumer
        self._router = router

    def subscribe(self) -> None:
        """Register all event subscriptions."""
        self._bus_consumer.subscribe(
            'chat_provider_created', self.on_provider_created,
        )
        self._bus_consumer.subscribe(
            'chat_provider_edited', self.on_provider_edited,
        )
        self._bus_consumer.subscribe(
            'chat_provider_deleted', self.on_provider_deleted,
        )
        self._bus_consumer.subscribe(
            'user_alias_created', self.on_user_alias_created,
        )
        self._bus_consumer.subscribe(
            'user_alias_deleted', self.on_user_alias_deleted,
        )

    def on_provider_created(self, event: dict[str, str]) -> None:
        logger.info('Chat provider created: %s', event.get('uuid'))
        self._router.invalidate_cache()

    def on_provider_edited(self, event: dict[str, str]) -> None:
        logger.info('Chat provider edited: %s', event.get('uuid'))
        self._router.invalidate_cache()

    def on_provider_deleted(self, event: dict[str, str]) -> None:
        logger.info('Chat provider deleted: %s', event.get('uuid'))
        self._router.invalidate_cache()

    def on_user_alias_created(self, event: dict[str, str]) -> None:
        logger.info('User alias created: %s', event.get('uuid'))
        self._router.invalidate_cache()

    def on_user_alias_deleted(self, event: dict[str, str]) -> None:
        logger.info('User alias deleted: %s', event.get('uuid'))
        self._router.invalidate_cache()
