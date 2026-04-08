# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

import requests

from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.plugins.connectors.exceptions import ConnectorSendError
from wazo_chatd.plugins.connectors.types import (
    InboundMessage,
    OutboundMessage,
    StatusUpdate,
    TransportData,
    WebhookData,
)

logger = logging.getLogger(__name__)

MOCK_URL = os.environ.get('TEST_CONNECTOR_MOCK_URL', 'http://connector-mock:8080')


class TestConnector:
    backend: ClassVar[str] = 'test'
    supported_types: ClassVar[tuple[str, ...]] = ('test', 'test_alt')
    status_map: ClassVar[dict[str, DeliveryStatus]] = {
        'sent': DeliveryStatus.SENT,
        'delivered': DeliveryStatus.DELIVERED,
        'failed': DeliveryStatus.FAILED,
    }

    def __init__(
        self,
        provider_config: Mapping[str, Any],
        connector_config: Mapping[str, Any],
    ) -> None:
        self._mock_url: str = MOCK_URL
        mock_url = provider_config.get('mock_url')
        if mock_url:
            self._mock_url = str(mock_url)

    def send(self, message: OutboundMessage) -> str:
        config = self._get_config()
        behavior = config.get('send_behavior', 'succeed')

        self._report_sent(message)

        if behavior == 'fail':
            raise ConnectorSendError(
                config.get('error_message', 'Test connector failure')
            )

        return config.get('external_id', f'test-{message.message_uuid}')

    @classmethod
    def can_handle(cls, data: TransportData) -> bool:
        match data:
            case WebhookData(headers=headers):
                return 'X-Test-Connector' in headers
            case _:
                return True

    @classmethod
    def on_event(cls, data: TransportData) -> InboundMessage | StatusUpdate | None:
        match data:
            case WebhookData(body=body):
                return cls._parse_webhook(body)
            case _:
                return None

    @classmethod
    def _parse_webhook(
        cls, body: Mapping[str, Any]
    ) -> InboundMessage | StatusUpdate | None:
        content = body.get('body')
        if content:
            return InboundMessage(
                sender=body.get('from', ''),
                recipient=body.get('to', ''),
                body=str(content),
                backend=cls.backend,
                message_type=body.get('type', 'test'),
                external_id=body.get('message_id', ''),
                metadata=dict(body),
            )

        status = body.get('status')
        external_id = body.get('external_id', '')
        if status and external_id:
            return StatusUpdate(
                external_id=external_id,
                status=status,
                backend=cls.backend,
                error_code=body.get('error_code', ''),
            )

        return None

    def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
        pass

    def stop(self) -> None:
        pass

    @classmethod
    def normalize_identity(cls, raw_identity: str) -> str:
        if raw_identity.startswith('test:'):
            return raw_identity
        raise ValueError(f'Test connector expects "test:" prefix: {raw_identity}')

    def _get_config(self) -> dict[str, str]:
        try:
            response = requests.get(f'{self._mock_url}/config', timeout=2)
            return response.json()
        except requests.RequestException:
            return {}

    def _report_sent(self, message: OutboundMessage) -> None:
        try:
            requests.post(
                f'{self._mock_url}/sent',
                json={
                    'message_uuid': message.message_uuid,
                    'message_type': message.message_type,
                    'sender_identity': message.sender_identity,
                    'recipient_identity': message.recipient_identity,
                    'body': message.body,
                },
                timeout=2,
            )
        except requests.RequestException:
            logger.warning('Failed to report sent message to mock')
