# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from wazo_chatd.plugins.connectors.helpers import transport_mode


class TestTransportMode(unittest.TestCase):
    def test_defaults_to_webhook_when_unconfigured(self) -> None:
        assert transport_mode({}, 'sms') == 'webhook'
        assert transport_mode({'sms': {}}, 'sms') == 'webhook'
        assert transport_mode({'sms': None}, 'sms') == 'webhook'

    def test_returns_configured_mode(self) -> None:
        assert transport_mode({'sms': {'mode': 'poll'}}, 'sms') == 'poll'
        assert transport_mode({'sms': {'mode': 'listen'}}, 'sms') == 'listen'
        assert transport_mode({'sms': {'mode': 'webhook'}}, 'sms') == 'webhook'

    def test_unknown_mode_falls_back_to_webhook(self) -> None:
        assert transport_mode({'sms': {'mode': 'polll'}}, 'sms') == 'webhook'

    def test_non_string_mode_falls_back_to_webhook(self) -> None:
        assert transport_mode({'sms': {'mode': True}}, 'sms') == 'webhook'
