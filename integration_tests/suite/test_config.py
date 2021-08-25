# Copyright 2019-2021 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
from hamcrest import assert_that, has_key, calling, has_properties
from xivo_test_helpers import until
from xivo_test_helpers.hamcrest.raises import raises

from .helpers.base import (
    APIIntegrationTest,
    use_asset,
    APIAssetLaunchingTestCase,
    CHATD_TOKEN_UUID,
)

from wazo_chatd_client.exceptions import ChatdError


@use_asset('base')
class TestConfig(APIIntegrationTest):
    def tearDown(self):
        self.reset_auth()

    def test_config(self):
        chatd_client = APIAssetLaunchingTestCase.make_chatd(CHATD_TOKEN_UUID)
        result = chatd_client.config.get()
        assert_that(result, has_key('rest_api'))

    def test_restrict_only_master_tenant(self):
        chatd_client = APIAssetLaunchingTestCase.make_chatd()
        assert_that(
            calling(chatd_client.config.get),
            raises(ChatdError, has_properties('status_code', 401)),
        )

    def test_restrict_on_with_slow_wazo_auth(self):
        APIAssetLaunchingTestCase.stop_service('chatd')
        APIAssetLaunchingTestCase.stop_service('auth')
        APIAssetLaunchingTestCase.start_service('chatd')

        chatd_client = APIAssetLaunchingTestCase.make_chatd(CHATD_TOKEN_UUID)

        def _returns_503():
            try:
                chatd_client.config.get()
            except ChatdError as e:
                assert e.status_code == 503
            except requests.RequestException as e:
                raise AssertionError(e)

        until.assert_(_returns_503, tries=10)

        APIAssetLaunchingTestCase.start_service('auth')

        def _not_return_503():
            try:
                response = chatd_client.config.get()
                assert_that(response, has_key('debug'))
            except Exception as e:
                raise AssertionError(e)

        until.assert_(_not_return_503, tries=10)
