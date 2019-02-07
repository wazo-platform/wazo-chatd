# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    equal_to,
    has_items,
)
from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy

TENANT_UUID = str(uuid.uuid4())
USER_UUID = str(uuid.uuid4())


class TestSession(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.session()
    def test_get(self, session):
        session = self._session_dao.get(session.uuid)
        assert_that(session, equal_to(session))

    @fixtures.db.session()
    @fixtures.db.session()
    def test_list(self, session_1, session_2):
        sessions = self._session_dao.list_()
        assert_that(sessions, has_items(session_1, session_2))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TENANT_UUID)
    @fixtures.db.session(user_uuid=USER_UUID)
    def test_tenant_uuid(self, tenant, _, session):
        assert_that(session.tenant_uuid, equal_to(tenant.uuid))
