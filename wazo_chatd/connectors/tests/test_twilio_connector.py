# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import pytest

from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage


class TestTwilioConnectorClassAttrs(unittest.TestCase):
    def test_backend(self) -> None:
        from wazo_chatd.connectors.backends.twilio import TwilioConnector

        assert TwilioConnector.backend == 'twilio'

    def test_supported_types(self) -> None:
        from wazo_chatd.connectors.backends.twilio import TwilioConnector

        assert 'sms' in TwilioConnector.supported_types
        assert 'mms' in TwilioConnector.supported_types
        assert 'whatsapp' in TwilioConnector.supported_types


class TestTwilioConnectorConfigure(unittest.TestCase):
    def setUp(self) -> None:
        from wazo_chatd.connectors.backends.twilio import TwilioConnector

        self.connector = TwilioConnector()

    def test_configure_stores_credentials(self) -> None:
        self.connector.configure(
            'sms',
            provider_config={
                'account_sid': 'AC123',
                'auth_token': 'secret',
            },
            connector_config={},
        )

        assert self.connector._type == 'sms'
        assert self.connector._account_sid == 'AC123'

    def test_configure_poll_mode(self) -> None:
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={'mode': 'poll', 'polling_interval': 15},
        )

        assert self.connector._mode == 'poll'
        assert self.connector._polling_interval == 15

    def test_configure_webhook_mode_default(self) -> None:
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )

        assert self.connector._mode == 'webhook'


class TestTwilioConnectorSend(unittest.TestCase):
    def setUp(self) -> None:
        from wazo_chatd.connectors.backends.twilio import TwilioConnector

        self.connector = TwilioConnector()
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )

    @patch('wazo_chatd.connectors.backends.twilio.TwilioRestClient')
    def test_send_creates_message(self, mock_client_cls: Mock) -> None:
        mock_client = Mock()
        mock_client.messages.create.return_value = Mock(sid='SM_MSG_123')
        mock_client_cls.return_value = mock_client
        self.connector._client = mock_client

        message = OutboundMessage(
            sender_alias='+15551234',
            recipient_alias='+15559876',
            sender_uuid='user-uuid',
            body='Hello from Wazo',
            delivery_uuid='delivery-uuid',
            metadata={'idempotency_key': 'key-1'},
        )

        result = self.connector.send(message)

        mock_client.messages.create.assert_called_once_with(
            to='+15559876',
            body='Hello from Wazo',
            from_='+15551234',
        )
        assert result == 'SM_MSG_123'

    @patch('wazo_chatd.connectors.backends.twilio.TwilioRestClient')
    def test_send_raises_on_failure(self, mock_client_cls: Mock) -> None:
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception('Twilio error')
        mock_client_cls.return_value = mock_client
        self.connector._client = mock_client

        message = OutboundMessage(
            sender_alias='+15551234',
            recipient_alias='+15559876',
            sender_uuid='user-uuid',
            body='Hello',
            delivery_uuid='delivery-uuid',
        )

        with pytest.raises(ConnectorSendError):
            self.connector.send(message)


class TestTwilioConnectorOnEvent(unittest.TestCase):
    def setUp(self) -> None:
        from wazo_chatd.connectors.backends.twilio import TwilioConnector

        self.connector = TwilioConnector()
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )

    def test_on_event_webhook_returns_inbound_message(self) -> None:
        raw_data = {
            'From': '+15559876',
            'To': '+15551234',
            'Body': 'Hello!',
            'MessageSid': 'SM_ABC_123',
            '_headers': {'User-Agent': 'TwilioProxy/1.1'},
            '_content_type': 'application/x-www-form-urlencoded',
        }

        result = self.connector.on_event('webhook', raw_data)

        assert result is not None
        assert isinstance(result, InboundMessage)
        assert result.sender == '+15559876'
        assert result.recipient == '+15551234'
        assert result.body == 'Hello!'
        assert result.backend == 'twilio'
        assert result.external_id == 'SM_ABC_123'

    def test_on_event_webhook_missing_body_returns_none(self) -> None:
        raw_data = {
            'From': '+15559876',
            'To': '+15551234',
            'MessageSid': 'SM_ABC_123',
            '_headers': {},
        }

        result = self.connector.on_event('webhook', raw_data)

        assert result is None

    def test_on_event_unknown_transport_returns_none(self) -> None:
        result = self.connector.on_event('unknown', {})

        assert result is None


class TestTwilioConnectorNormalizeIdentity(unittest.TestCase):
    def setUp(self) -> None:
        from wazo_chatd.connectors.backends.twilio import TwilioConnector

        self.connector = TwilioConnector()

    def test_valid_e164(self) -> None:
        assert self.connector.normalize_identity('+15551234567') == '+15551234567'

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError):
            self.connector.normalize_identity('not-a-phone')

    def test_email_raises(self) -> None:
        with pytest.raises(ValueError):
            self.connector.normalize_identity('user@example.com')

    def test_short_number_raises(self) -> None:
        with pytest.raises(ValueError):
            self.connector.normalize_identity('+123')
