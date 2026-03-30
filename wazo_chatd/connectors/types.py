# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RoomParticipant:
    """A room participant extracted from ORM for cross-process transfer."""

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
class PipeCommand:
    """Base class for all commands sent between processes via pipe."""


@dataclass(frozen=True)
class Ping(PipeCommand):
    """Sent via pipe to check worker health."""


@dataclass(frozen=True)
class Pong(PipeCommand):
    """Sent via pipe in response to a Ping."""


@dataclass(frozen=True)
class Ready(PipeCommand):
    """Sent via pipe by the worker after initialization is complete."""


@dataclass(frozen=True)
class ConfigSync(PipeCommand):
    """Sent via pipe during server process initialization.

    Contains the full list of provider configurations so the server
    process can reconstruct connector instances without DB access.
    """

    providers: list[dict[str, Any]]


@dataclass(frozen=True)
class ConfigUpdate(PipeCommand):
    """Sent via pipe at runtime when a provider configuration changes."""

    action: str
    """One of 'add', 'update', 'remove'."""

    provider: dict[str, Any]
