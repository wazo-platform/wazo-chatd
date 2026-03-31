# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, ClassVar

import requests

from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

MOCK_URL = os.environ.get(
    'TEST_CONNECTOR_MOCK_URL', 'http://connector-mock:8080'
)


class TestConnector:
    backend: ClassVar[str] = 'test'
    supported_types: ClassVar[tuple[str, ...]] = ('test',)

    def __init__(self) -> None:
        self._type: str = ''
        self._mock_url: str = MOCK_URL

    def configure(
        self,
        type_: str,
        provider_config: Mapping[str, Any],
        connector_config: Mapping[str, Any],
    ) -> None:
        self._type = type_
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

    def can_handle(
        self,
        transport: str,
        raw_data: Mapping[str, Any],
    ) -> bool:
        if transport != 'webhook':
            return True
        headers = raw_data.get('_headers', {})
        return 'X-Test-Connector' in headers

    def on_event(
        self,
        transport: str,
        raw_data: Mapping[str, Any],
    ) -> InboundMessage | None:
        if transport != 'webhook':
            return None

        body = raw_data.get('body')
        if not body:
            return None

        return InboundMessage(
            sender=raw_data.get('from', ''),
            recipient=raw_data.get('to', ''),
            body=str(body),
            backend=self.backend,
            external_id=raw_data.get('message_id', ''),
            metadata={
                k: v
                for k, v in raw_data.items()
                if not k.startswith('_')
            },
        )

    def listen(self, on_message: Callable[[InboundMessage], None]) -> None:
        pass

    def stop(self) -> None:
        pass

    def normalize_identity(self, raw_identity: str) -> str:
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
                    'sender_alias': message.sender_alias,
                    'recipient_alias': message.recipient_alias,
                    'body': message.body,
                },
                timeout=2,
            )
        except requests.RequestException:
            logger.warning('Failed to report sent message to mock')
