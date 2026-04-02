# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Internal wazo-to-wazo chat connector.

This is the simplest possible :class:`~wazo_chatd.plugins.connectors.connector.Connector`
implementation.  It handles messages between Wazo users where no
external API is involved — the bus event published by
:class:`RoomService` **is** the delivery mechanism.

Use this module as a reference when implementing a new connector
backend.  Every method is annotated to explain *why* it behaves the
way it does.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    TransportData,
)


class InternalConnector:
    """No-op connector for wazo-to-wazo messaging."""

    backend: ClassVar[str] = 'wazo'
    supported_types: ClassVar[tuple[str, ...]] = ('internal',)
    status_map: ClassVar[dict[str, DeliveryStatus]] = {}

    def configure(
        self,
        type_: str,
        provider_config: Mapping[str, Any],
        connector_config: Mapping[str, Any],
    ) -> None:
        """No configuration needed for internal messaging."""

    def send(self, message: OutboundMessage) -> str:
        """No-op.  Internal messages are delivered via bus events,
        not through an external API.

        Returns an empty string (no external message ID).
        """
        return ''

    def can_handle(self, data: TransportData) -> bool:
        """Internal connector never handles external events."""
        return False

    def on_event(self, data: TransportData) -> None:
        """Internal connector has no external inbound events."""
        return None

    def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
        """No-op.  Internal messages arrive through the room API
        directly, not from an external source."""

    def stop(self) -> None:
        """Nothing to clean up."""

    def normalize_identity(self, raw_identity: str) -> str:
        """Wazo identities are UUIDs — reject non-UUID formats."""
        try:
            uuid.UUID(raw_identity)
        except ValueError:
            raise ValueError(
                f'Internal connector only handles UUID identities: {raw_identity}'
            )
        return raw_identity
