# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from wazo_chatd.plugin_helpers.tenant import make_uuid5


class TestMakeUuid5(unittest.TestCase):
    def test_deterministic(self) -> None:
        result_a = make_uuid5('tenant-1', '+15551234')
        result_b = make_uuid5('tenant-1', '+15551234')
        assert result_a == result_b

    def test_different_tenants_produce_different_uuids(self) -> None:
        result_a = make_uuid5('tenant-1', '+15551234')
        result_b = make_uuid5('tenant-2', '+15551234')
        assert result_a != result_b

    def test_different_keys_produce_different_uuids(self) -> None:
        result_a = make_uuid5('tenant-1', '+15551234')
        result_b = make_uuid5('tenant-1', '+15559876')
        assert result_a != result_b
