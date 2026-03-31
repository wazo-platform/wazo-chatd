# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
import unittest
import unittest.mock
from unittest.mock import AsyncMock, Mock

from wazo_chatd.connectors.loop import DeliveryLoop
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage


def _make_config() -> dict[str, str | bool]:
    return {
        'db_uri': 'postgresql://localhost/test',
        'uuid': 'svc-uuid',
        'bus': {},
    }


def _make_outbound() -> OutboundMessage:
    return OutboundMessage(
        room_uuid='room-uuid',
        message_uuid='msg-uuid',
        sender_uuid='user-uuid',
        body='hello',
    )


def _make_inbound() -> InboundMessage:
    return InboundMessage(
        sender='+15559876',
        recipient='+15551234',
        body='hello',
        backend='twilio',
        external_id='ext-123',
    )


class TestDeliveryLoopLifecycle(unittest.TestCase):
    @unittest.mock.patch('wazo_chatd.connectors.loop.init_async_db')
    @unittest.mock.patch('wazo_chatd.connectors.loop.BusPublisher')
    def test_start_creates_loop_thread(
        self, mock_bus: Mock, mock_init_db: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), Mock(return_value=AsyncMock()))
        mock_bus.from_config.return_value = Mock()

        loop = DeliveryLoop(_make_config(), Mock(), {})
        loop.start()

        try:
            assert loop._loop is not None
            assert loop._loop.is_running()
            assert loop._thread is not None
            assert loop._thread.is_alive()
        finally:
            loop.shutdown()

    @unittest.mock.patch('wazo_chatd.connectors.loop.init_async_db')
    @unittest.mock.patch('wazo_chatd.connectors.loop.BusPublisher')
    def test_shutdown_stops_loop(
        self, mock_bus: Mock, mock_init_db: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), Mock(return_value=AsyncMock()))
        mock_bus.from_config.return_value = Mock()

        loop = DeliveryLoop(_make_config(), Mock(), {})
        loop.start()
        loop.shutdown()

        assert not loop._thread.is_alive()

    @unittest.mock.patch('wazo_chatd.connectors.loop.init_async_db')
    @unittest.mock.patch('wazo_chatd.connectors.loop.BusPublisher')
    def test_context_manager(
        self, mock_bus: Mock, mock_init_db: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), Mock(return_value=AsyncMock()))
        mock_bus.from_config.return_value = Mock()

        with DeliveryLoop(_make_config(), Mock(), {}) as loop:
            assert loop._loop.is_running()

        assert not loop._thread.is_alive()


class TestDeliveryLoopStatus(unittest.TestCase):
    @unittest.mock.patch('wazo_chatd.connectors.loop.init_async_db')
    @unittest.mock.patch('wazo_chatd.connectors.loop.BusPublisher')
    def test_is_running_when_started(
        self, mock_bus: Mock, mock_init_db: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), Mock(return_value=AsyncMock()))
        mock_bus.from_config.return_value = Mock()

        loop = DeliveryLoop(_make_config(), Mock(), {})
        loop.start()

        try:
            assert loop.is_running is True
        finally:
            loop.shutdown()

    def test_is_not_running_when_not_started(self) -> None:
        loop = DeliveryLoop(_make_config(), Mock(), {})

        assert loop.is_running is False


class TestDeliveryLoopEnqueue(unittest.TestCase):
    @unittest.mock.patch('wazo_chatd.connectors.loop.init_async_db')
    @unittest.mock.patch('wazo_chatd.connectors.loop.BusPublisher')
    def test_enqueue_outbound_creates_task(
        self, mock_bus: Mock, mock_init_db: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), Mock(return_value=AsyncMock()))
        mock_bus.from_config.return_value = Mock()

        with DeliveryLoop(_make_config(), Mock(), {}) as loop:
            loop.enqueue_message(_make_outbound())
            time.sleep(0.1)

            assert loop._executor is not None

    @unittest.mock.patch('wazo_chatd.connectors.loop.init_async_db')
    @unittest.mock.patch('wazo_chatd.connectors.loop.BusPublisher')
    def test_enqueue_inbound_creates_task(
        self, mock_bus: Mock, mock_init_db: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), Mock(return_value=AsyncMock()))
        mock_bus.from_config.return_value = Mock()

        with DeliveryLoop(_make_config(), Mock(), {}) as loop:
            loop.enqueue_message(_make_inbound())
            time.sleep(0.1)

            assert loop._executor is not None
