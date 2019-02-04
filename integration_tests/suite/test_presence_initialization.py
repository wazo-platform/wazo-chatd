# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    contains_inanyorder,
    has_properties,
)

from .helpers import fixtures
from .helpers.wait_strategy import NoWaitStrategy, EverythingOkWaitStrategy
from .helpers.base import (
    BaseIntegrationTest,
    VALID_TOKEN,
)


class TestPresenceInitialization(BaseIntegrationTest):

    asset = 'initialization'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.tenant()
    @fixtures.db.tenant()
    def test_initialization(self, tenant_unchanged, tenant_deleted):
        tenant_created_uuid = str(uuid.uuid4())
        self.auth.set_tenants({
            'items': [
                {'uuid': tenant_created_uuid},
                {'uuid': tenant_unchanged.uuid},
            ]
        })

        self.restart_service('chatd')
        self.chatd = self.make_chatd(VALID_TOKEN)
        EverythingOkWaitStrategy().wait(self)

        tenants = self._tenant_dao.list_()
        assert_that(tenants, contains_inanyorder(
            has_properties(uuid=tenant_unchanged.uuid),
            has_properties(uuid=tenant_created_uuid),
        ))
