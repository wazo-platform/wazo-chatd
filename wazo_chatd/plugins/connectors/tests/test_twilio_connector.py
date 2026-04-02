# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import hashlib
import hmac
import unittest
from urllib.parse import urlencode
from unittest.mock import Mock, patch

import pytest

from wazo_chatd.plugins.connectors.backends.twilio import TwilioConnector
from wazo_chatd.plugins.connectors.exceptions import ConnectorSendError
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
    TransportData,
    WebhookData,
)


class TestTwilioConnectorClassAttrs(unittest.TestCase):
    def test_backend(self) -> None:
        assert TwilioConnector.backend == 'twilio'

    def test_supported_types(self) -> None:
        assert 'sms' in TwilioConnector.supported_types
        assert 'mms' in TwilioConnector.supported_types
        assert 'whatsapp' in TwilioConnector.supported_types


class TestTwilioConnectorConfigure(unittest.TestCase):
    def setUp(self) -> None:
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
        self.connector = TwilioConnector()
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )

    @patch('wazo_chatd.plugins.connectors.backends.twilio.TwilioRestClient')
    def test_send_creates_message(self, mock_client_cls: Mock) -> None:
        mock_client = Mock()
        mock_client.messages.create.return_value = Mock(sid='SM_MSG_123')
        mock_client_cls.return_value = mock_client
        self.connector._client = mock_client  # type: ignore[assignment]

        message = OutboundMessage(
            room_uuid='room-uuid',
            message_uuid='delivery-uuid',
            sender_uuid='user-uuid',
            body='Hello from Wazo',
            sender_alias='+15551234',
            recipient_alias='+15559876',
            metadata={'idempotency_key': 'key-1'},
        )

        result = self.connector.send(message)

        mock_client.messages.create.assert_called_once_with(
            to='+15559876',
            body='Hello from Wazo',
            from_='+15551234',
        )
        assert result == 'SM_MSG_123'

    @patch('wazo_chatd.plugins.connectors.backends.twilio.TwilioRestClient')
    def test_send_raises_on_failure(self, mock_client_cls: Mock) -> None:
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception('Twilio error')
        mock_client_cls.return_value = mock_client
        self.connector._client = mock_client  # type: ignore[assignment]

        message = OutboundMessage(
            room_uuid='room-uuid',
            message_uuid='delivery-uuid',
            sender_uuid='user-uuid',
            body='Hello',
            sender_alias='+15551234',
            recipient_alias='+15559876',
        )

        with pytest.raises(ConnectorSendError):
            self.connector.send(message)


class TestTwilioConnectorCanHandle(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = TwilioConnector()

    def test_webhook_with_twilio_signature(self) -> None:
        data = WebhookData(
            body={},
            headers={
                'X-Twilio-Signature': 'abc123',
                'User-Agent': 'TwilioProxy/1.1',
            },
        )

        assert self.connector.can_handle(data) is True

    def test_webhook_without_signature(self) -> None:
        data = WebhookData(
            body={},
            headers={'User-Agent': 'SomeOtherAgent'},
        )

        assert self.connector.can_handle(data) is False

    def test_webhook_no_headers(self) -> None:
        assert self.connector.can_handle(WebhookData()) is False

    def test_non_webhook_transport(self) -> None:
        assert self.connector.can_handle(TransportData()) is True


class TestTwilioConnectorOnEvent(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = TwilioConnector()
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )

    def test_on_event_webhook_returns_inbound_message(self) -> None:
        data = _signed_webhook({
            'From': '+15559876',
            'To': '+15551234',
            'Body': 'Hello!',
            'MessageSid': 'SM_ABC_123',
        })

        result = self.connector.on_event(data)

        assert result is not None
        assert isinstance(result, InboundMessage)
        assert result.sender == '+15559876'
        assert result.recipient == '+15551234'
        assert result.body == 'Hello!'
        assert result.backend == 'twilio'
        assert result.external_id == 'SM_ABC_123'

    def test_on_event_webhook_missing_body_returns_none(self) -> None:
        data = _signed_webhook({
            'From': '+15559876',
            'To': '+15551234',
            'MessageSid': 'SM_ABC_123',
        })

        result = self.connector.on_event(data)

        assert result is None

    def test_on_event_unknown_transport_returns_none(self) -> None:
        result = self.connector.on_event(TransportData())

        assert result is None


class TestTwilioConnectorStatusUpdate(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = TwilioConnector()
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )

    def test_status_callback_returns_status_update(self) -> None:
        data = _signed_webhook({
            'MessageSid': 'SM_ABC_123',
            'MessageStatus': 'delivered',
            'To': '+15551234',
            'From': '+15559876',
        })

        result = self.connector.on_event(data)

        assert isinstance(result, StatusUpdate)
        assert result.external_id == 'SM_ABC_123'
        assert result.status == 'delivered'
        assert result.backend == 'twilio'

    def test_failed_status_includes_error_code(self) -> None:
        data = _signed_webhook({
            'MessageSid': 'SM_ABC_123',
            'MessageStatus': 'failed',
            'ErrorCode': '30003',
        })

        result = self.connector.on_event(data)

        assert isinstance(result, StatusUpdate)
        assert result.status == 'failed'
        assert result.error_code == '30003'

    def test_message_with_body_returns_inbound_not_status(self) -> None:
        data = _signed_webhook({
            'MessageSid': 'SM_ABC_123',
            'MessageStatus': 'received',
            'Body': 'Hello!',
            'From': '+15559876',
            'To': '+15551234',
        })

        result = self.connector.on_event(data)

        assert isinstance(result, InboundMessage)
        assert result.body == 'Hello!'

    def test_no_body_no_status_returns_none(self) -> None:
        data = _signed_webhook({
            'MessageSid': 'SM_ABC_123',
        })

        result = self.connector.on_event(data)

        assert result is None


_TEST_URL = 'https://chatd.example.com/1.0/connectors/incoming/twilio'
_TEST_AUTH_TOKEN = 'secret'


def _compute_twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    data = url + ''.join(f'{k}{v}' for k, v in sorted(params.items()))
    mac = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def _signed_webhook(body: dict[str, str], url: str = _TEST_URL) -> WebhookData:
    signature = _compute_twilio_signature(_TEST_AUTH_TOKEN, url, body)
    return WebhookData(
        body=body,
        headers={'X-Twilio-Signature': signature},
        url=url,
    )


class TestTwilioConnectorSignatureValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = TwilioConnector()
        self.connector.configure(
            'sms',
            provider_config={'account_sid': 'AC123', 'auth_token': 'secret'},
            connector_config={},
        )
        self.url = 'https://chatd.example.com/1.0/connectors/incoming/twilio'
        self.body = {
            'From': '+15559876',
            'To': '+15551234',
            'Body': 'Hello!',
            'MessageSid': 'SM_ABC_123',
        }

    def test_valid_signature_returns_message(self) -> None:
        signature = _compute_twilio_signature('secret', self.url, self.body)
        data = WebhookData(
            body=self.body,
            headers={'X-Twilio-Signature': signature},
            url=self.url,
        )

        result = self.connector.on_event(data)

        assert isinstance(result, InboundMessage)
        assert result.body == 'Hello!'

    def test_invalid_signature_returns_none(self) -> None:
        data = WebhookData(
            body=self.body,
            headers={'X-Twilio-Signature': 'forged-signature'},
            url=self.url,
        )

        result = self.connector.on_event(data)

        assert result is None

    def test_missing_signature_returns_none(self) -> None:
        data = WebhookData(
            body=self.body,
            headers={},
            url=self.url,
        )

        result = self.connector.on_event(data)

        assert result is None

    def test_unconfigured_auth_token_returns_none(self) -> None:
        connector = TwilioConnector()
        connector.configure('sms', provider_config={}, connector_config={})

        signature = _compute_twilio_signature('', self.url, self.body)
        data = WebhookData(
            body=self.body,
            headers={'X-Twilio-Signature': signature},
            url=self.url,
        )

        result = connector.on_event(data)

        assert result is None


class TestTwilioConnectorNormalizeIdentity(unittest.TestCase):
    def setUp(self) -> None:
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
