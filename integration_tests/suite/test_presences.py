# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import (
    assert_that,
    contains,
    equal_to,
    has_entries,
)

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest


class TestPresences(BaseIntegrationTest):

    asset = 'base'

    @fixtures.db.user()
    @fixtures.db.user()
    def test_list(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(presences, has_entries(
            items=contains(user_1, user_2),
            total=equal_to(2),
            filtered=equal_to(2),
        ))
