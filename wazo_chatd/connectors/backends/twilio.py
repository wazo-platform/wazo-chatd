# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Twilio connector backend.

Supports SMS, MMS, WhatsApp, and Messenger via the Twilio REST API.
Can operate in webhook mode (chatd receives Twilio webhooks) or poll
mode (connector polls Twilio API for new messages).

Requires the ``twilio`` Python package at runtime.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from typing import ClassVar

from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# E.164 phone number: + followed by 7-15 digits
_E164_PATTERN = re.compile(r'^\+[1-9]\d{6,14}$')


def _get_twilio_client_class() -> type | None:
    try:
        from twilio.rest import Client

        return Client
    except ImportError:
        logger.warning(
            'twilio package not installed — '
            'TwilioConnector.send() will not work until installed'
        )
        return None


TwilioRestClient = _get_twilio_client_class


class TwilioConnector:
    """Twilio messaging connector.

    Implements the :class:`~wazo_chatd.connectors.connector.Connector`
    protocol for Twilio's REST API.
    """

    backend: ClassVar[str] = 'twilio'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms', 'whatsapp', 'messenger')

    def __init__(self) -> None:
        self._type: str = ''
        self._account_sid: str = ''
        self._auth_token: str = ''
        self._client = None  # type: ignore[var-annotated]
        self._mode: str = 'webhook'
        self._polling_interval: int = 30
        self._stopped: bool = False

    def configure(
        self,
        type_: str,
        provider_config: Mapping[str, str],
        connector_config: Mapping[str, str | int],
    ) -> None:
        self._type = type_
        self._account_sid = provider_config.get('account_sid', '')
        self._auth_token = provider_config.get('auth_token', '')
        self._mode = str(connector_config.get('mode', 'webhook'))
        self._polling_interval = int(connector_config.get('polling_interval', 30))

        if self._account_sid and self._auth_token:
            client_cls = TwilioRestClient()
            if client_cls:
                self._client = client_cls(self._account_sid, self._auth_token)

    def send(self, message: OutboundMessage) -> str:
        if self._client is None:
            raise ConnectorSendError('Twilio client not configured')

        try:
            result = self._client.messages.create(  # type: ignore[union-attr]
                to=message.recipient_alias,
                body=message.body,
                from_=message.sender_alias,
            )
            return result.sid
        except Exception as exc:
            raise ConnectorSendError(str(exc)) from exc

    def can_handle(
        self,
        transport: str,
        raw_data: Mapping[str, str],
    ) -> bool:
        if transport != 'webhook':
            return True

        headers = raw_data.get('_headers', {})
        return 'X-Twilio-Signature' in headers

    def on_event(
        self,
        transport: str,
        raw_data: Mapping[str, str],
    ) -> InboundMessage | None:
        if transport == 'webhook':
            return self._parse_webhook(raw_data)
        elif transport == 'poll':
            return self._parse_poll_result(raw_data)
        return None

    def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
        if self._mode == 'poll':
            self._poll_loop(on_message)
        # webhook mode: no-op — chatd's HTTP adapter calls on_event directly

    def stop(self) -> None:
        self._stopped = True

    def normalize_identity(self, raw_identity: str) -> str:
        if _E164_PATTERN.match(raw_identity):
            return raw_identity
        raise ValueError(f'Not a valid E.164 phone number: {raw_identity}')

    def _parse_webhook(self, raw_data: Mapping[str, str]) -> InboundMessage | None:
        """Parse a Twilio webhook payload into an InboundMessage."""
        sender = raw_data.get('From', '')
        recipient = raw_data.get('To', '')
        body = raw_data.get('Body')
        message_sid = raw_data.get('MessageSid', '')

        if not body:
            return None

        return InboundMessage(
            sender=sender,
            recipient=recipient,
            body=body,
            backend=self.backend,
            external_id=message_sid,
            metadata=dict(raw_data),
        )

    def _parse_poll_result(self, raw_data: Mapping[str, str]) -> InboundMessage | None:
        """Parse a Twilio API message resource into an InboundMessage."""
        sender = raw_data.get('from_', '')
        recipient = raw_data.get('to', '')
        body = raw_data.get('body')
        sid = raw_data.get('sid', '')

        if not body:
            return None

        return InboundMessage(
            sender=sender,
            recipient=recipient,
            body=body,
            backend=self.backend,
            external_id=sid,
            metadata=dict(raw_data),
        )

    def _poll_loop(self, on_message: Callable[[InboundMessage], None]) -> None:
        """Poll Twilio API for new messages."""
        import time

        while not self._stopped:
            # TODO: implement actual polling logic
            #  - query Twilio messages API with date_sent filter
            #  - track last_seen message SID to avoid duplicates
            #  - call on_event('poll', msg_dict) for each new message
            time.sleep(self._polling_interval)
