# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.connectors.delivery import MAX_RETRIES, DeliveryStatus
from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.types import ConfigSync, OutboundMessage


def _make_outbound(delivery_uuid: str = 'delivery-1') -> OutboundMessage:
    return OutboundMessage(
        sender_alias='+15551234',
        recipient_alias='+15559876',
        sender_uuid='user-uuid',
        body='hello',
        delivery_uuid=delivery_uuid,
        metadata={'idempotency_key': 'key-1'},
    )


class _FakeConnector:
    backend = 'twilio'
    supported_types = ('sms',)

    def __init__(self) -> None:
        self.send_return = 'ext-msg-id-123'
        self.send_side_effect: Exception | None = None

    def configure(self, type_, provider_config, connector_config) -> None:
        pass

    def send(self, message: OutboundMessage) -> str:
        if self.send_side_effect:
            raise self.send_side_effect
        return self.send_return


class TestDeliveryExecutorLoadFromPipe(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Mock()
        self.registry.get_backend.return_value = _FakeConnector
        self.executor = DeliveryExecutor(
            registry=self.registry,
            connector_config={},
        )

    def test_load_from_pipe_creates_instances(self) -> None:
        config_sync = ConfigSync(
            providers=[
                {
                    'name': 'twilio-sms',
                    'type': 'sms',
                    'backend': 'twilio',
                    'configuration': {'account_sid': 'test'},
                },
            ]
        )

        self.executor.load_from_pipe(config_sync)

        assert 'twilio-sms' in self.executor.connectors
        self.registry.get_backend.assert_called_with('twilio')

    def test_load_from_pipe_multiple_providers(self) -> None:
        config_sync = ConfigSync(
            providers=[
                {
                    'name': 'twilio-sms',
                    'type': 'sms',
                    'backend': 'twilio',
                    'configuration': {},
                },
                {
                    'name': 'twilio-mms',
                    'type': 'mms',
                    'backend': 'twilio',
                    'configuration': {},
                },
            ]
        )

        self.executor.load_from_pipe(config_sync)

        assert len(self.executor.connectors) == 2


class TestDeliveryExecutorExecute(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.registry = Mock()
        self.connector = _FakeConnector()
        self.executor = DeliveryExecutor(
            registry=self.registry,
            connector_config={},
        )
        self.executor.connectors['twilio-sms'] = self.connector  # type: ignore[assignment]

        self.delivery = Mock()
        self.delivery.message_uuid = 'delivery-1'
        self.delivery.backend = 'twilio'
        self.delivery.retry_count = 0
        self.delivery.external_id = None

        self.session = Mock()
        self.bus_publisher = Mock()

    async def test_execute_success(self) -> None:
        outbound = _make_outbound()

        await self.executor.execute(
            outbound,
            self.delivery,
            self.session,
            self.bus_publisher,
        )

        assert self.delivery.external_id == 'ext-msg-id-123'
        # Should have added SENDING then SENT records
        assert self.session.add.call_count >= 2
        self.session.flush.assert_called()

    async def test_execute_failure_increments_retry(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')
        outbound = _make_outbound()

        await self.executor.execute(
            outbound,
            self.delivery,
            self.session,
            self.bus_publisher,
        )

        assert self.delivery.retry_count == 1

    async def test_execute_max_retries_sets_dead_letter(self) -> None:
        self.connector.send_side_effect = ConnectorSendError('timeout')
        self.delivery.retry_count = MAX_RETRIES - 1
        outbound = _make_outbound()

        await self.executor.execute(
            outbound,
            self.delivery,
            self.session,
            self.bus_publisher,
        )

        # Should have a DEAD_LETTER record
        added_objects = [call.args[0] for call in self.session.add.call_args_list]
        statuses = [obj.status for obj in added_objects if hasattr(obj, 'status')]
        assert DeliveryStatus.DEAD_LETTER.value in statuses
