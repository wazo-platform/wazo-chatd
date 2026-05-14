# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from xivo.rest_api_helpers import APIException


class ConnectorError(Exception):
    """Base exception for all connector-related errors."""


class ConnectorSendError(ConnectorError):
    """Raised when a connector fails to send a message."""


class ConnectorRateLimited(ConnectorSendError):
    """Provider rate-limited the call; ``retry_after`` is the requested back-off in seconds."""

    def __init__(self, message: str, *, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ConnectorParseError(ConnectorError):
    """Raised when a connector fails to parse an incoming event."""


class ConnectorTransientError(ConnectorError):
    """Raised when an inbound event can't be processed right now but
    should be retried by the provider — e.g. wazo-auth unreachable, or
    the connector instance hasn't been populated yet at startup."""


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


class NoSuchConnectorException(APIException):
    def __init__(self, backend: str) -> None:
        super().__init__(
            404,
            f'No such connector {backend!r}',
            'no-such-connector',
            {'backend': backend},
            'connectors',
        )


class InventoryNotSupportedException(APIException):
    def __init__(self, backend: str) -> None:
        super().__init__(
            501,
            f'Connector {backend!r} does not support inventory listing',
            'inventory-not-supported',
            {'backend': backend},
            'connectors',
        )


class InventoryUnavailableException(APIException):
    def __init__(self, backend: str) -> None:
        super().__init__(
            502,
            f'Connector {backend!r} failed to list provider inventory',
            'inventory-unavailable',
            {'backend': backend},
            'connectors',
        )


class BackendNotConfiguredException(APIException):
    def __init__(self, backend: str, tenant_uuid: str) -> None:
        super().__init__(
            400,
            f'Backend {backend!r} is not configured for tenant {tenant_uuid!r}',
            'backend-not-configured',
            {'backend': backend, 'tenant_uuid': tenant_uuid},
            'identities',
        )


class AuthServiceUnavailableException(APIException):
    def __init__(self) -> None:
        super().__init__(
            503,
            'wazo-auth is unreachable',
            'wazo-auth-unreachable',
            {},
            'identities',
        )


class ConnectorAuthException(APIException):
    def __init__(self) -> None:
        super().__init__(
            401,
            'Webhook signature verification failed',
            'connector-signature-invalid',
            {},
            'connectors',
        )


class WebhookParseException(APIException):
    def __init__(self) -> None:
        super().__init__(
            400,
            'Unrecognized request',
            'webhook-parse-error',
            {},
            'connectors',
        )


class WebhookTransientException(APIException):
    def __init__(self) -> None:
        super().__init__(
            503,
            'Service temporarily unavailable',
            'webhook-transient',
            {},
            'connectors',
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
