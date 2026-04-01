# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
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
        'delivery': {'max_concurrent_tasks': 100},
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


class TestDeliveryLoopRestart(unittest.TestCase):
    def _make_loop(self) -> DeliveryLoop:
        loop = DeliveryLoop(_make_config(), Mock(), {})
        loop._loop = asyncio.new_event_loop()
        loop._semaphore = asyncio.Semaphore(100)
        loop._max_tasks = 100
        return loop

    def test_restart_increments_count(self) -> None:
        loop = self._make_loop()
        with unittest.mock.patch.object(loop, '_run_loop'):
            with unittest.mock.patch('wazo_chatd.connectors.loop.time.sleep'):
                loop._restart()
                assert loop.restart_count == 1
                loop._restart()
                assert loop.restart_count == 2

    def test_restart_backoff_increases(self) -> None:
        loop = self._make_loop()
        delays: list[int] = []
        with unittest.mock.patch.object(loop, '_run_loop'):
            with unittest.mock.patch(
                'wazo_chatd.connectors.loop.time.sleep',
                side_effect=lambda d: delays.append(d),
            ):
                for _ in range(4):
                    loop._restart()
        assert delays == [1, 2, 4, 8]

    def test_restart_resets_backoff_when_healthy(self) -> None:
        loop = self._make_loop()
        delays: list[int] = []
        with unittest.mock.patch.object(loop, '_run_loop'):
            with unittest.mock.patch(
                'wazo_chatd.connectors.loop.time.sleep',
                side_effect=lambda d: delays.append(d),
            ):
                loop._restart()
                loop._restart()
                assert delays == [1, 2]

                loop._healthy = True
                loop._restart()
                assert delays[-1] == 1
