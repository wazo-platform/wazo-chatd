# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from wazo_chatd.connectors.server import HealthCheck, MessageServer, Sentinel
from wazo_chatd.connectors.types import ConfigSync, ConfigUpdate, OutboundMessage


def _make_outbound(delivery_uuid: str = 'delivery-1') -> OutboundMessage:
    return OutboundMessage(
        sender_alias='+15551234',
        recipient_alias='+15559876',
        sender_uuid='user-uuid',
        body='hello',
        delivery_uuid=delivery_uuid,
    )


class TestMessageServerQueue(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MessageServer()

    def test_send_message_puts_on_queue(self) -> None:
        outbound = _make_outbound()

        self.server.send_message(outbound)

        item = self.server._queue.get(timeout=1)
        assert isinstance(item, OutboundMessage)
        assert item.delivery_uuid == 'delivery-1'

    def test_send_message_delayed(self) -> None:
        outbound = _make_outbound()

        self.server.send_message(outbound, delay=0.01)

        import time

        time.sleep(0.05)
        item = self.server._queue.get_nowait()
        assert isinstance(item, OutboundMessage)
        assert item.delivery_uuid == 'delivery-1'


class TestMessageServerPipe(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MessageServer()

    def test_pipe_send_config_sync(self) -> None:
        config_sync = ConfigSync(providers=[{'name': 'test', 'backend': 'twilio'}])

        self.server.pipe_send(config_sync)

        data = self.server._worker_connection.recv()
        assert isinstance(data, ConfigSync)
        assert len(data.providers) == 1

    def test_pipe_send_config_update(self) -> None:
        update = ConfigUpdate(action='add', provider={'name': 'new'})

        self.server.pipe_send(update)

        data = self.server._worker_connection.recv()
        assert isinstance(data, ConfigUpdate)
        assert data.action == 'add'


class TestMessageServerShutdown(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MessageServer()

    def test_shutdown_sends_sentinel(self) -> None:
        self.server.shutdown(timeout=1)

        item = self.server._queue.get(timeout=1)
        assert item is Sentinel.SHUTDOWN


class TestMessageServerPing(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MessageServer()

    def test_ping_receives_pong(self) -> None:
        import threading

        def respond_pong() -> None:
            if self.server._worker_connection.poll(timeout=2):
                msg = self.server._worker_connection.recv()
                if msg is HealthCheck.PING:
                    self.server._worker_connection.send(HealthCheck.PONG)

        responder = threading.Thread(target=respond_pong)
        responder.start()

        result = self.server.ping(timeout=2)
        responder.join()

        assert result is True

    def test_ping_returns_false_on_timeout(self) -> None:
        result = self.server.ping(timeout=0.1)

        assert result is False
