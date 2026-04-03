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


class NoCommonConnectorError(APIException):
    def __init__(self) -> None:
        super().__init__(
            409,
            'Room participants share no common connector type',
            'no-common-connector',
            {},
            'rooms',
        )


class MessageAliasRequiredError(APIException):
    def __init__(self) -> None:
        super().__init__(
            409,
            'Messages in rooms with external participants require a sender_alias_uuid',
            'message-alias-required',
            {},
            'messages',
        )


class InvalidAliasError(APIException):
    def __init__(self, alias_uuid: str) -> None:
        super().__init__(
            400,
            f'No alias found with UUID {alias_uuid!r}',
            'invalid-alias',
            {'alias_uuid': alias_uuid},
            'messages',
        )


class UnreachableParticipantError(APIException):
    def __init__(self, participant: str, connector_type: str = '') -> None:
        detail = f'participant {participant!r}'
        if connector_type:
            detail += f' via {connector_type!r}'
        super().__init__(
            409,
            f'No connector can reach {detail}',
            'unreachable-participant',
            {'participant': participant, 'connector_type': connector_type},
            'rooms',
        )
