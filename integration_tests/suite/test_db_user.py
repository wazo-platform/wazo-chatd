# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    equal_to,
    has_items,
    has_properties,
    is_not,
    none,
)
from sqlalchemy.inspection import inspect

from wazo_chatd.database.models import User
from wazo_chatd.exceptions import UnknownUserException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import (
    BaseIntegrationTest,
    UNKNOWN_UUID,
    MASTER_TENANT_UUID,
    SUBTENANT_UUID,
)


class TestUser(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'

    def test_create(self):
        user_uuid = uuid.uuid4()
        user = User(
            uuid=user_uuid,
            tenant_uuid=MASTER_TENANT_UUID,
            state='AVAILABLE',
            status='description of available state',
        )
        user = self._user_dao.create(user)

        self._session.expire_all()
        assert_that(inspect(user).persistent)
        assert_that(user, has_properties(
            uuid=str(user_uuid),
            tenant_uuid=MASTER_TENANT_UUID,
        ))

    @fixtures.db.user()
    def test_get(self, user):
        user_uuid = user.uuid
        result = self._user_dao.get([MASTER_TENANT_UUID], user_uuid)

        assert_that(result, has_properties(
            uuid=user_uuid,
        ))

        # TODO: add test get SUBTENAN_UUID

    @fixtures.db.user()
    @fixtures.db.user(tenant_uuid=SUBTENANT_UUID)
    def test_list(self, user_1, user_2):
        result = self._user_dao.list_([MASTER_TENANT_UUID])
        assert_that(result, has_items(user_1))

        result = self._user_dao.list_([MASTER_TENANT_UUID, SUBTENANT_UUID])
        assert_that(result, has_items(user_1, user_2))

        result = self._user_dao.list_([SUBTENANT_UUID])
        assert_that(result, has_items(user_2))

    @fixtures.db.user()
    @fixtures.db.user(tenant_uuid=SUBTENANT_UUID)
    def test_list_bypass_tenant(self, user_1, user_2):
        result = self._user_dao.list_(tenant_uuids=None)
        assert_that(result, has_items(user_1, user_2))

    @fixtures.db.user()
    @fixtures.db.user()
    def test_count(self, user_1, user_2):
        result = self._user_dao.count([MASTER_TENANT_UUID])
        assert_that(result, equal_to(2))

        # TODO: add test count SUBTENAN_UUID

    def test_get_doesnt_exist(self):
        assert_that(
            calling(self._user_dao.get).with_args(
                [MASTER_TENANT_UUID],
                UNKNOWN_UUID,
            ),
            raises(
                UnknownUserException,
                has_properties(
                    status_code=404,
                    id_='unknown-user',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                )
            )
        )

    @fixtures.db.user()
    def test_update(self, user):
        user_uuid = user.uuid
        user_state = 'INVISIBLE'
        user_status = 'other status'

        user.state = user_state
        user.status = user_status
        self._user_dao.update(user)

        self._session.expire_all()
        assert_that(user, has_properties(
            uuid=user_uuid,
            state=user_state,
            status=user_status,
        ))
