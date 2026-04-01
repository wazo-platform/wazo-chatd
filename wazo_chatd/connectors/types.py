# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TransportData:
    """Base class for transport-specific event data.

    Subclass this to define new transport types. wazo-chatd provides
    :class:`WebhookData` for HTTP webhooks. Connector developers can
    create their own subclasses for custom transports.

    No required fields — each subclass defines its own structure.

    Use structural pattern matching to dispatch::

        match data:
            case WebhookData(headers=headers, body=body):
                ...validate signature using headers...
            case MyCustomTransport(source=source):
                ...handle custom transport...
    """


@dataclass(frozen=True)
class WebhookData(TransportData):
    """Data from an HTTP webhook request."""

    body: Mapping[str, Any] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    content_type: str = ''


@dataclass(frozen=True)
class RoomParticipant:
    """A room participant extracted from ORM for cross-thread transfer."""

    uuid: str
    identity: str | None


@dataclass(frozen=True)
class OutboundMessage:
    """A message to be sent through a connector to an external system."""

    room_uuid: str
    message_uuid: str
    sender_uuid: str
    body: str
    participants: tuple[RoomParticipant, ...] = ()
    sender_alias: str = ''
    recipient_alias: str = ''
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f'OutboundMessage(message={self.message_uuid})'


@dataclass(frozen=True)
class InboundMessage:
    """A message received from an external system through a connector."""

    sender: str
    """External identity of the sender (phone number, email, etc.)."""

    recipient: str
    """External identity of the recipient."""

    body: str
    """Message content."""

    backend: str
    """Which backend produced this message (e.g. "twilio")."""

    external_id: str
    """The backend's message ID, for idempotency and tracking."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Backend-specific extra data.

    If the provider supplies an idempotency key, include it as
    ``idempotency_key``.  The router uses this to deduplicate inbound
    messages via a GIN-indexed JSONB lookup on MessageMeta.extra.
    """

    def __str__(self) -> str:
        return f'InboundMessage(backend={self.backend}, external_id={self.external_id})'


@dataclass(frozen=True)
class StatusUpdate:
    """A delivery status update received from an external system."""

    external_id: str
    """The backend's message ID that this status refers to."""

    status: str
    """Provider-specific status string (e.g. 'delivered', 'failed')."""

    backend: str
    """Which backend produced this update (e.g. 'twilio')."""

    error_code: str = ''
    """Provider error code if the delivery failed."""

    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f'StatusUpdate(backend={self.backend}, external_id={self.external_id}, status={self.status})'
