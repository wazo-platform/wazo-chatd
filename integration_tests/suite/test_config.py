# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
from hamcrest import assert_that, has_key, calling, has_properties
from wazo_test_helpers import until
from wazo_test_helpers.hamcrest.raises import raises

from .helpers.base import (
    APIIntegrationTest,
    use_asset,
    TOKEN_SUBTENANT_UUID,
    START_TIMEOUT,
)

from wazo_chatd_client.exceptions import ChatdError


@use_asset('base')
class TestConfig(APIIntegrationTest):
    def test_config(self):
        result = self.chatd.config.get()
        assert_that(result, has_key('rest_api'))

    def test_restrict_only_master_tenant(self):
        chatd_client = self.asset_cls.make_chatd(str(TOKEN_SUBTENANT_UUID))
        assert_that(
            calling(chatd_client.config.get),
            raises(ChatdError, has_properties('status_code', 401)),
        )

    def test_restrict_on_with_slow_wazo_auth(self):
        self.stop_chatd_service()
        self.stop_auth_service()
        self.start_chatd_service()

        def _returns_503():
            try:
                self.chatd.config.get()
            except ChatdError as e:
                assert e.status_code == 503
            except requests.RequestException as e:
                raise AssertionError(e)

        until.assert_(_returns_503, timeout=START_TIMEOUT)

        self.start_auth_service()

        def _not_return_503():
            try:
                response = self.chatd.config.get()
                assert_that(response, has_key('debug'))
            except Exception as e:
                raise AssertionError(e)

        until.assert_(_not_return_503, timeout=START_TIMEOUT)
