# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from xivo.rest_api_helpers import APIException


class ConnectorError(Exception):
    """Base exception for all connector-related errors."""


class ConnectorSendError(ConnectorError):
    """Raised when a connector fails to send a message."""


class ConnectorParseError(ConnectorError):
    """Raised when a connector fails to parse an incoming event."""


class NoCommonConnectorError(ConnectorError):
    """Raised when room participants share no common connector type.

    This typically results in a 409 Conflict HTTP response.
    """


class MessageAliasRequiredError(APIException):
    def __init__(self) -> None:
        super().__init__(
            409,
            'Messages in rooms with external participants require a sender_alias_uuid',
            'message-alias-required',
            {},
            'messages',
        )


class UnreachableParticipantError(APIException):
    def __init__(self, identity: str) -> None:
        super().__init__(
            409,
            f'No connector can reach participant with identity {identity!r}',
            'unreachable-participant',
            {'identity': identity},
            'rooms',
        )
