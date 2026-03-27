# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations


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
