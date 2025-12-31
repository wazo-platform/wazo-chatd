# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import assert_that, calling, has_entry, has_key, has_properties
from wazo_chatd_client.exceptions import ChatdError
from wazo_test_helpers import until
from wazo_test_helpers.hamcrest.raises import raises

from .helpers.base import (
    START_TIMEOUT,
    TOKEN_SUBTENANT_UUID,
    APIIntegrationTest,
    use_asset,
)


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

    def test_restrict_when_service_token_not_initialized(self):
        def _returns_503():
            assert_that(
                calling(self.chatd.config.get),
                raises(ChatdError).matching(
                    has_properties(
                        status_code=503,
                        error_id='not-initialized',
                    )
                ),
            )

        config = {'auth': {'username': 'invalid-service'}}
        with self.chatd_with_config(config):
            until.assert_(_returns_503, timeout=START_TIMEOUT)

    def test_patch_config_restrict_to_master_tenant(self):
        patch_body = [{'op': 'replace', 'path': '/debug', 'value': 'false'}]

        chatd_client = self.asset_cls.make_chatd(str(TOKEN_SUBTENANT_UUID))
        assert_that(
            calling(chatd_client.config.patch).with_args(patch_body),
            raises(ChatdError, has_properties('status_code', 401)),
        )

    def test_patch_config_live_debug(self):
        patch_body = [{'op': 'replace', 'path': '/debug', 'value': 'true'}]

        result = self.chatd.config.patch(patch_body)
        assert_that(result, has_entry('debug', True))

        patch_body = [{'op': 'replace', 'path': '/debug', 'value': 'false'}]
        result = self.chatd.config.patch(patch_body)
        assert_that(result, has_entry('debug', False))

    def test_that_empty_body_for_patch_config_returns_400(self):
        self.assert_empty_body_returns_400([('patch', 'config')])
