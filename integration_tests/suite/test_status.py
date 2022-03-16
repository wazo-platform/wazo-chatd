# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import assert_that, has_entries, has_entry
from wazo_test_helpers import until

from .helpers.base import APIIntegrationTest, use_asset


@use_asset('base')
class TestStatusAllOK(APIIntegrationTest):
    def test_when_status_then_status_ok(self):
        def status_ok():
            result = self.chatd.status.get()
            assert_that(
                result,
                has_entries(
                    rest_api=has_entry('status', 'ok'),
                    bus_consumer=has_entry('status', 'ok'),
                ),
            )

        until.assert_(status_ok, timeout=5)
