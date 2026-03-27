# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from wazo_chatd.plugins.rooms.schemas import UserAliasListRequestSchema


class TestUserAliasListRequestSchema(unittest.TestCase):
    def test_load_single_type(self) -> None:
        result = UserAliasListRequestSchema().load({'type': 'sms'})

        assert result['types'] == ['sms']

    def test_load_multiple_types_comma_separated(self) -> None:
        result = UserAliasListRequestSchema().load({'type': 'sms,whatsapp'})

        assert sorted(result['types']) == ['sms', 'whatsapp']

    def test_load_no_type_returns_empty(self) -> None:
        result = UserAliasListRequestSchema().load({})

        assert result['types'] == []

    def test_load_strips_whitespace(self) -> None:
        result = UserAliasListRequestSchema().load({'type': ' sms , whatsapp '})

        assert sorted(result['types']) == ['sms', 'whatsapp']
