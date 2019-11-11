# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import assert_that, calling, equal_to, has_items

from wazo_chatd.exceptions import UnknownSessionException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy

TENANT_UUID = str(uuid.uuid4())
USER_UUID = str(uuid.uuid4())
UNKNOWN_UUID = str(uuid.uuid4())


class TestSession(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.session()
    def test_get(self, session):
        result = self._dao.session.get(session.uuid)
        assert_that(result, equal_to(session))

        assert_that(
            calling(self._dao.session.get).with_args(UNKNOWN_UUID),
            raises(UnknownSessionException),
        )

    @fixtures.db.session()
    @fixtures.db.session()
    def test_list(self, session_1, session_2):
        sessions = self._dao.session.list_()
        assert_that(sessions, has_items(session_1, session_2))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TENANT_UUID)
    @fixtures.db.session(user_uuid=USER_UUID)
    def test_tenant_uuid(self, tenant, _, session):
        assert_that(session.tenant_uuid, equal_to(tenant.uuid))

    @fixtures.db.session(mobile=False)
    def test_update(self, session):
        mobile = True
        session.mobile = mobile
        self._dao.session.update(session)

        self._session.expire_all()
        assert_that(session.mobile, equal_to(mobile))
