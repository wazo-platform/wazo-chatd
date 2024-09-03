# Copyright 2019-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import signal
from unittest import TestCase
from unittest.mock import Mock

from ..controller import _signal_handler


class TestController(TestCase):
    def test_sigterm_handler(self) -> None:
        mock_controller = Mock()
        _signal_handler(mock_controller, signal.SIGTERM, Mock())
        mock_controller.stop.assert_called_once_with(reason="SIGTERM")
