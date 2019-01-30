# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import (
    assert_that,
    contains,
    equal_to,
    has_entries,
)

from .helpers import fixtures
from .helpers.base import (
    BaseIntegrationTest,
    SUBTENANT_UUID,
)


class TestPresences(BaseIntegrationTest):

    asset = 'base'

    @fixtures.db.user()
    @fixtures.db.user()
    def test_list(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(presences, has_entries(
            items=contains(
                has_entries(
                    uuid=user_1.uuid,
                    tenant_uuid=user_1.tenant_uuid,
                    state=user_1.state,
                    status=user_1.status,
                ),
                has_entries(
                    uuid=user_2.uuid,
                    tenant_uuid=user_2.tenant_uuid,
                    state=user_2.state,
                    status=user_2.status,
                ),
            ),
            total=equal_to(2),
            filtered=equal_to(2),
        ))

    @fixtures.db.user()
    @fixtures.db.user(tenant_uuid=SUBTENANT_UUID)
    def test_list_multi_tenant(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(presences, has_entries(
            items=contains(has_entries(uuid=user_1.uuid)),
            total=equal_to(1),
            filtered=equal_to(1),
        ))

        presences = self.chatd.user_presences.list(recurse=True)
        assert_that(presences, has_entries(
            items=contains(has_entries(uuid=user_1.uuid), has_entries(uuid=user_2.uuid)),
            total=equal_to(2),
            filtered=equal_to(2),
        ))
