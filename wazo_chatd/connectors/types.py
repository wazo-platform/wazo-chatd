# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True)
class ConnectorConfig:
    """Full list of provider configurations for connector initialization."""

    providers: list[dict[str, Any]]


@dataclass(frozen=True)
class ConnectorConfigUpdate:
    """A runtime configuration change for a single provider."""

    action: str
    """One of 'add', 'update', 'remove'."""

    provider: dict[str, Any]
