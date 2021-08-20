# Copyright 2019-2021 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import assert_that, has_key

from .helpers.base import (
    APIIntegrationTest,
    use_asset,
    APIAssetLaunchingTestCase,
    CHATD_TOKEN_UUID,
)


@use_asset('base')
class TestConfig(APIIntegrationTest):
    def test_config(self):
        chatd_client = APIAssetLaunchingTestCase.make_chatd(CHATD_TOKEN_UUID)
        result = chatd_client.config.get()
        assert_that(result, has_key('rest_api'))
