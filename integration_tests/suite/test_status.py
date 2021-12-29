# Copyright 2019-2021 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import assert_that, has_entries
from wazo_test_helpers import until

from .helpers.base import APIIntegrationTest, use_asset


@use_asset('base')
class TestStatusAllOK(APIIntegrationTest):
    def test_when_status_then_status_ok(self):
        def status_ok():
            result = self.chatd.status.get()
            assert_that(result['rest_api'], has_entries({'status': 'ok'}))

        until.assert_(status_ok, timeout=5)
