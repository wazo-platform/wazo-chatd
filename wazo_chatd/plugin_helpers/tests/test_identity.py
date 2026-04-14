# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from wazo_chatd.plugin_helpers.identity import derive_external_user_uuid


class TestDeriveExternalUserUuid(unittest.TestCase):
    def test_deterministic(self) -> None:
        result_a = derive_external_user_uuid('tenant-1', '+15551234')
        result_b = derive_external_user_uuid('tenant-1', '+15551234')
        assert result_a == result_b

    def test_different_tenants_produce_different_uuids(self) -> None:
        result_a = derive_external_user_uuid('tenant-1', '+15551234')
        result_b = derive_external_user_uuid('tenant-2', '+15551234')
        assert result_a != result_b

    def test_different_identities_produce_different_uuids(self) -> None:
        result_a = derive_external_user_uuid('tenant-1', '+15551234')
        result_b = derive_external_user_uuid('tenant-1', '+15559876')
        assert result_a != result_b
