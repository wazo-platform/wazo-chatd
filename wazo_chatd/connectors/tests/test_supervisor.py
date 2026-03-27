# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.connectors.supervisor import WorkerSupervisor


class TestWorkerSupervisor(unittest.TestCase):
    def setUp(self) -> None:
        self.server = Mock()
        self.server.process = Mock()
        self.server.process.is_alive.return_value = True
        self.server.process.exitcode = None
        self.server.ping.return_value = True
        self.router = Mock()
        self.supervisor = WorkerSupervisor(self.server, self.router)

    def test_provide_status_ok_when_alive_and_responsive(self) -> None:
        status: dict = {}  # type: ignore[type-arg]

        self.supervisor.provide_status(status)

        assert status['message_worker']['status'] == 'ok'
        assert status['message_worker']['restart_count'] == 0

    def test_provide_status_fail_when_dead(self) -> None:
        self.server.process.is_alive.return_value = False
        status: dict = {}  # type: ignore[type-arg]

        self.supervisor.provide_status(status)

        assert status['message_worker']['status'] == 'fail'

    def test_provide_status_fail_when_unresponsive(self) -> None:
        self.server.process.is_alive.return_value = True
        self.server.ping.return_value = False
        status: dict = {}  # type: ignore[type-arg]

        self.supervisor.provide_status(status)

        assert status['message_worker']['status'] == 'fail'

    def test_shutdown_stops_server(self) -> None:
        self.supervisor.shutdown(timeout=5)

        self.server.shutdown.assert_called_once_with(timeout=5)

    def test_restart_count_starts_at_zero(self) -> None:
        assert self.supervisor.restart_count == 0
