# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    contains_inanyorder,
    has_properties,
)

from .helpers import fixtures
from .helpers.wait_strategy import EverythingOkWaitStrategy
from .helpers.base import (
    BaseIntegrationTest,
    VALID_TOKEN,
)

TENANT_UUID = str(uuid.uuid4())


class TestPresenceInitialization(BaseIntegrationTest):

    asset = 'initialization'
    wait_strategy = EverythingOkWaitStrategy()

    @fixtures.db.tenant()
    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(tenant_uuid=TENANT_UUID)
    @fixtures.db.user(tenant_uuid=TENANT_UUID)
    def test_initialization(self, tenant_deleted, tenant_unchanged, user_deleted, user_unchanged):
        # setup tenants
        tenant_created_uuid = str(uuid.uuid4())
        self.auth.set_tenants({
            'items': [
                {'uuid': tenant_created_uuid},
                {'uuid': tenant_unchanged.uuid},
            ]
        })

        # setup users
        user_created_uuid = str(uuid.uuid4())
        self.confd.set_users(
            {'uuid': user_created_uuid, 'tenant_uuid': tenant_created_uuid},
            {'uuid': user_unchanged.uuid, 'tenant_uuid': user_unchanged.tenant_uuid},
        )

        self.restart_service('chatd')
        self.chatd = self.make_chatd(VALID_TOKEN)
        EverythingOkWaitStrategy().wait(self)

        # test tenants
        tenants = self._tenant_dao.list_()
        assert_that(tenants, contains_inanyorder(
            has_properties(uuid=tenant_unchanged.uuid),
            has_properties(uuid=tenant_created_uuid),
        ))

        # test users
        users = self._user_dao.list_(tenant_uuids=None)
        assert_that(users, contains_inanyorder(
            has_properties(uuid=user_unchanged.uuid),
            has_properties(uuid=user_created_uuid),
        ))
