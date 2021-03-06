# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import assert_that, has_key

from .helpers.base import APIIntegrationTest, use_asset


@use_asset('base')
class TestConfig(APIIntegrationTest):
    def test_config(self):
        result = self.chatd.config.get()

        assert_that(result, has_key('rest_api'))
