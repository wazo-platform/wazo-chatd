# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import (
    assert_that,
    has_key,
)

from .helpers.base import BaseIntegrationTest


class TestConfig(BaseIntegrationTest):

    asset = 'base'

    def test_config(self):
        result = self.chatd.config.get()

        assert_that(result, has_key('rest_api'))
