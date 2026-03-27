# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import multiprocessing as mp
import threading
import time
import unittest
from unittest.mock import Mock

from wazo_chatd.connectors.server import PING, PONG, MessageServer, Sentinel
from wazo_chatd.connectors.types import ConfigSync, ConfigUpdate, OutboundMessage


def _make_outbound(delivery_uuid: str = 'delivery-1') -> OutboundMessage:
    return OutboundMessage(
        sender_alias='+15551234',
        recipient_alias='+15559876',
        sender_uuid='user-uuid',
        body='hello',
        delivery_uuid=delivery_uuid,
    )


def _make_server() -> MessageServer:
    return MessageServer({}, Mock())


def _make_server_with_pipe() -> MessageServer:
    server = _make_server()
    server._main_connection, server._worker_connection = mp.Pipe()
    return server


class TestMessageServerQueue(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server()

    def test_send_message_puts_on_queue(self) -> None:
        outbound = _make_outbound()

        self.server.send_message(outbound)

        item = self.server._queue.get(timeout=1)
        assert isinstance(item, OutboundMessage)
        assert item.delivery_uuid == 'delivery-1'

    def test_send_message_delayed(self) -> None:
        outbound = _make_outbound()

        self.server.send_message(outbound, delay=0.01)

        time.sleep(0.05)
        item = self.server._queue.get_nowait()
        assert isinstance(item, OutboundMessage)
        assert item.delivery_uuid == 'delivery-1'


class TestMessageServerPipe(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server_with_pipe()

    def test_pipe_send_config_sync(self) -> None:
        config_sync = ConfigSync(providers=[{'name': 'test', 'backend': 'twilio'}])

        self.server.pipe_send(config_sync)

        assert self.server._worker_connection is not None
        data = self.server._worker_connection.recv()
        assert isinstance(data, ConfigSync)
        assert len(data.providers) == 1

    def test_pipe_send_config_update(self) -> None:
        update = ConfigUpdate(action='add', provider={'name': 'new'})

        self.server.pipe_send(update)

        assert self.server._worker_connection is not None
        data = self.server._worker_connection.recv()
        assert isinstance(data, ConfigUpdate)
        assert data.action == 'add'


class TestMessageServerShutdown(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _make_server()

    def test_shutdown_sends_sentinel(self) -> None:
        self.server.shutdown(timeout=1)

        item = self.server._queue.get(timeout=1)
        assert item is Sentinel.SHUTDOWN


class TestMessageServerPing(unittest.TestCase):
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


class TestMessageServerStatus(unittest.TestCase):
    def test_restart_count_starts_at_zero(self) -> None:
        server = _make_server()

        assert server.restart_count == 0

    def test_provide_status_fail_when_not_started(self) -> None:
        server = _make_server()
        status: dict[str, dict[str, str | int]] = {}

        server.provide_status(status)

        assert status['message_worker']['status'] == 'fail'
        assert status['message_worker']['restart_count'] == 0
