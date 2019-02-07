# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    has_properties,
    has_items,
    not_,
)
from xivo_test_helpers import until

from wazo_chatd.database import models
from .helpers import fixtures
from .helpers.base import BaseIntegrationTest

USER_UUID_1 = str(uuid.uuid4())


class TestEventHandler(BaseIntegrationTest):

    asset = 'base'

    def test_user_created(self):
        user_uuid = str(uuid.uuid4())
        tenant_uuid = str(uuid.uuid4())
        self.bus.send_user_created_event(user_uuid, tenant_uuid)

        def user_created():
            result = self._user_dao.list_(tenant_uuids=None)
            assert_that(result, has_items(
                has_properties(uuid=user_uuid, tenant_uuid=tenant_uuid),
            ))

        until.assert_(user_created, tries=3)

    @fixtures.db.user()
    def test_user_deleted(self, user):
        user_uuid = user.uuid
        tenant_uuid = user.tenant_uuid
        self.bus.send_user_deleted_event(user_uuid, tenant_uuid)

        def user_deleted():
            result = self._user_dao.list_(tenant_uuids=None)
            assert_that(result, not_(has_items(
                has_properties(uuid=user_uuid, tenant_uuid=tenant_uuid),
            )))

        until.assert_(user_deleted, tries=3)

    def test_tenant_created(self):
        tenant_uuid = str(uuid.uuid4())
        self.bus.send_tenant_created_event(tenant_uuid)

        def tenant_created():
            result = self._tenant_dao.list_()
            assert_that(result, has_items(
                has_properties(uuid=tenant_uuid),
            ))

        until.assert_(tenant_created, tries=3)

    @fixtures.db.tenant()
    def test_tenant_deleted(self, tenant):
        tenant_uuid = tenant.uuid
        self.bus.send_tenant_deleted_event(tenant_uuid)

        def tenant_deleted():
            result = self._tenant_dao.list_()
            assert_that(result, not_(has_items(
                has_properties(uuid=tenant_uuid),
            )))

        until.assert_(tenant_deleted, tries=3)

    @fixtures.db.user()
    def test_session_created(self, user):
        session_uuid = str(uuid.uuid4())
        user_uuid = user.uuid
        self.bus.send_session_created_event(session_uuid, user_uuid, user.tenant_uuid)

        def session_created():
            result = self._session.query(models.Session).all()
            assert_that(result, has_items(
                has_properties(uuid=session_uuid, user_uuid=user_uuid),
            ))

        until.assert_(session_created, tries=3)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.session(user_uuid=USER_UUID_1)
    def test_session_deleted(self, user, session):
        session_uuid = session.uuid
        user_uuid = user.uuid
        self.bus.send_session_deleted_event(session_uuid, user_uuid, user.tenant_uuid)

        def session_deleted():
            result = self._session.query(models.Session).all()
            assert_that(result, not_(has_items(
                has_properties(uuid=session_uuid, user_uuid=user_uuid),
            )))

        until.assert_(session_deleted, tries=3)
