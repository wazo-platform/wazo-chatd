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


class NoCommonConnectorException(APIException):
    def __init__(self) -> None:
        super().__init__(
            409,
            'Room participants share no common connector type',
            'no-common-connector',
            {},
            'rooms',
        )


class MessageIdentityRequiredException(APIException):
    def __init__(self) -> None:
        super().__init__(
            409,
            'Messages in rooms with external participants require a sender_identity_uuid',
            'message-identity-required',
            {},
            'messages',
        )


class InvalidIdentityException(APIException):
    def __init__(self, identity_uuid: str) -> None:
        super().__init__(
            400,
            f'No identity found with UUID {identity_uuid!r}',
            'invalid-identity',
            {'identity_uuid': identity_uuid},
            'messages',
        )


class InvalidIdentityFormatException(APIException):
    def __init__(self, identity: str, backend: str, reason: str) -> None:
        super().__init__(
            400,
            f'Identity {identity!r} is not valid for backend {backend!r}: {reason}',
            'invalid-identity-format',
            {'identity': identity, 'backend': backend, 'reason': reason},
            'identities',
        )


class UnknownBackendException(APIException):
    def __init__(self, backend: str) -> None:
        super().__init__(
            400,
            f'Unknown connector backend {backend!r}',
            'unknown-backend',
            {'backend': backend},
            'identities',
        )


class AuthServiceUnavailableException(APIException):
    def __init__(self) -> None:
        super().__init__(
            503,
            'wazo-auth is unreachable',
            'wazo-auth-unreachable',
            {},
        )


class UnreachableParticipantException(APIException):
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
