# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import multiprocessing as mp
import threading
import time
import unittest
import unittest.mock
from unittest.mock import Mock

from wazo_chatd.connectors.manager import PING, PONG, DeliveryManager
from wazo_chatd.connectors.types import (
    ConfigSync,
    ConfigUpdate,
    InboundMessage,
    OutboundMessage,
    Sentinel,
)
from wazo_chatd.connectors.worker import Worker


def _make_outbound(message_uuid: str = 'delivery-1') -> OutboundMessage:
    return OutboundMessage(
        room_uuid='room-uuid',
        message_uuid=message_uuid,
        sender_uuid='user-uuid',
        body='hello',
    )


def _make_server() -> DeliveryManager:
    return DeliveryManager({}, Mock())


def _make_server_with_pipe() -> DeliveryManager:
    server = _make_server()
    server._main_connection, server._worker_connection = mp.Pipe()
    return server


class TestDeliveryManagerQueue(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server()

    def test_send_message_puts_on_queue(self) -> None:
        outbound = _make_outbound()

        self.server.enqueue_message(outbound)

        item = self.server._queue.get(timeout=1)
        assert isinstance(item, OutboundMessage)
        assert item.message_uuid == 'delivery-1'

    def test_send_message_delayed(self) -> None:
        outbound = _make_outbound()

        self.server.enqueue_message(outbound, delay=0.01)

        time.sleep(0.05)
        item = self.server._queue.get_nowait()
        assert isinstance(item, OutboundMessage)
        assert item.message_uuid == 'delivery-1'


class TestDeliveryManagerPipe(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server_with_pipe()

    def test_sync_config(self) -> None:
        providers = [{'name': 'test', 'backend': 'twilio'}]

        self.server.sync_config(providers)

        assert self.server._worker_connection is not None
        data = self.server._worker_connection.recv()
        assert isinstance(data, ConfigSync)
        assert len(data.providers) == 1

    def test_pipe_send_config_update(self) -> None:
        update = ConfigUpdate(action='add', provider={'name': 'new'})

        self.server._pipe_send(update)

        assert self.server._worker_connection is not None
        data = self.server._worker_connection.recv()
        assert isinstance(data, ConfigUpdate)
        assert data.action == 'add'


class TestDeliveryManagerShutdown(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server()

    def test_shutdown_sends_sentinel(self) -> None:
        self.server._queue.put(Sentinel.SHUTDOWN)
        item = self.server._queue.get(timeout=1)
        assert item is Sentinel.SHUTDOWN


class TestDeliveryManagerPing(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server_with_pipe()

    def test_ping_receives_pong(self) -> None:
        assert self.server._worker_connection is not None
        conn = self.server._worker_connection

        def respond_pong() -> None:
            if conn.poll(timeout=2):
                msg = conn.recv()
                if msg == PING:
                    conn.send(PONG)

        responder = threading.Thread(target=respond_pong)
        responder.start()

        result = self.server.ping(timeout=2)
        responder.join()

        assert result is True

    def test_ping_returns_false_on_timeout(self) -> None:
        result = self.server.ping(timeout=0.1)

        assert result is False


class TestWorkerInit(unittest.TestCase):
    def test_bootstrap_sets_engine_session_and_publisher(self) -> None:
        queue: mp.Queue[OutboundMessage | InboundMessage | Sentinel] = mp.Queue()
        conn, _ = mp.Pipe()
        worker = Worker(queue, conn)

        with unittest.mock.patch(
            'wazo_chatd.connectors.worker.init_async_db'
        ) as mock_init_db, unittest.mock.patch(
            'wazo_chatd.connectors.worker.BusPublisher'
        ) as mock_bus, unittest.mock.patch(
            'wazo_chatd.connectors.worker.ConnectorRegistry'
        ), unittest.mock.patch(
            'wazo_chatd.connectors.worker.setproctitle'
        ):
            mock_engine = Mock()
            mock_factory = Mock()
            mock_init_db.return_value = (mock_engine, mock_factory)
            mock_publisher = Mock()
            mock_bus.from_config.return_value = mock_publisher

            worker.bootstrap(
                {'db_uri': 'postgresql://localhost/test', 'uuid': 'svc', 'bus': {}}
            )

        assert worker._engine is mock_engine
        assert worker._session_factory is mock_factory
        assert worker._notifier is not None


class TestDeliveryManagerStatus(unittest.TestCase):
    def test_restart_count_starts_at_zero(self) -> None:
        server = _make_server()

        assert server.restart_count == 0

    def test_provide_status_fail_when_not_started(self) -> None:
        server = _make_server()
        status: dict[str, dict[str, str | int]] = {}

        server.provide_status(status)

        assert status['message_worker']['status'] == 'fail'
        assert status['message_worker']['restart_count'] == 0
