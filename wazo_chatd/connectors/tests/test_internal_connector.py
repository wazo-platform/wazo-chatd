# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

import pytest

from wazo_chatd.connectors.backends.internal import InternalConnector
from wazo_chatd.connectors.types import OutboundMessage


class TestInternalConnector(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = InternalConnector()
        self.connector.configure('internal', {}, {})

    def test_backend(self) -> None:
        assert InternalConnector.backend == 'wazo'

    def test_supported_types(self) -> None:
        assert InternalConnector.supported_types == ('internal',)

    def test_send_returns_empty_string(self) -> None:
        message = OutboundMessage(
            room_uuid='room-uuid',
            message_uuid='delivery-uuid',
            sender_uuid='some-uuid',
            body='hello',
        )

        result = self.connector.send(message)

        assert result == ''

    def test_on_event_returns_none(self) -> None:
        result = self.connector.on_event('webhook', {'data': 'test'})

        assert result is None

    def test_listen_does_not_call_on_message(self) -> None:
        on_message = Mock()

        self.connector.listen(on_message)

        on_message.assert_not_called()

    def test_stop_does_not_raise(self) -> None:
        self.connector.stop()

    def test_normalize_identity_accepts_uuid(self) -> None:
        identity = '00000000-0000-0000-0000-000000000001'

        result = self.connector.normalize_identity(identity)

        assert result == identity

    def test_normalize_identity_rejects_non_uuid(self) -> None:
        with pytest.raises(ValueError):
            self.connector.normalize_identity('test:+15551234')
