# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime
import random
import uuid
from typing import TYPE_CHECKING

from hamcrest import (
    assert_that,
    calling,
    contains,
    empty,
    equal_to,
    has_items,
    has_properties,
    is_not,
    none,
)
from sqlalchemy.inspection import inspect
from wazo_test_helpers.hamcrest.raises import raises

if TYPE_CHECKING:
    # NOTE(clanglois): this can be removed with sqlalchemy 2.0,
    #  as inspect should be typed correctly
    from sqlalchemy_stubs import InstanceState

from wazo_chatd.database.models import Line, RefreshToken, Session, User
from wazo_chatd.exceptions import UnknownUserException

from .helpers import fixtures
from .helpers.base import TOKEN_SUBTENANT_UUID as TENANT_2
from .helpers.base import TOKEN_TENANT_UUID as TENANT_1
from .helpers.base import UNKNOWN_UUID, DBIntegrationTest, use_asset

USER_UUID = uuid.uuid4()


@use_asset('database')
class TestUser(DBIntegrationTest):
    def test_create(self):
        user_uuid = uuid.uuid4()
        last_activity = datetime.datetime.now(datetime.UTC)
        user = User(
            uuid=user_uuid,
            tenant_uuid=TENANT_1,
            state='available',
            status='description of available state',
            last_activity=last_activity,
            do_not_disturb=True,
        )
        user = self._dao.user.create(user)

        self._session.expire_all()
        inspect_result: InstanceState = inspect(user)
        assert_that(inspect_result.persistent)
        assert_that(
            user,
            has_properties(
                uuid=user_uuid,
                tenant_uuid=TENANT_1,
                state='available',
                status='description of available state',
                last_activity=last_activity,
                do_not_disturb=True,
            ),
        )

    @fixtures.db.user(tenant_uuid=TENANT_1)
    @fixtures.db.user(tenant_uuid=TENANT_2)
    def test_get(self, user_1, user_2):
        result = self._dao.user.get([user_1.tenant_uuid], user_1.uuid)
        assert_that(result, equal_to(user_1))

        assert_that(
            calling(self._dao.user.get).with_args([user_2.tenant_uuid], user_1.uuid),
            raises(UnknownUserException, has_properties(status_code=404)),
        )

    def test_get_doesnt_exist(self):
        assert_that(
            calling(self._dao.user.get).with_args([TENANT_1], UNKNOWN_UUID),
            raises(
                UnknownUserException,
                has_properties(
                    status_code=404,
                    id_='unknown-user',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                ),
            ),
        )

    @fixtures.db.user(tenant_uuid=TENANT_1)
    @fixtures.db.user(tenant_uuid=TENANT_2)
    def test_list(self, user_1, user_2):
        result = self._dao.user.list_([user_1.tenant_uuid])
        assert_that(result, has_items(user_1))

        result = self._dao.user.list_([user_1.tenant_uuid, user_2.tenant_uuid])
        assert_that(result, has_items(user_1, user_2))

    @fixtures.db.user(tenant_uuid=TENANT_1)
    @fixtures.db.user(tenant_uuid=TENANT_2)
    def test_list_bypass_tenant(self, user_1, user_2):
        result = self._dao.user.list_(tenant_uuids=None)
        assert_that(result, has_items(user_1, user_2))

    @fixtures.db.user()
    @fixtures.db.user()
    @fixtures.db.user()
    def test_list_uuids(self, user_1, user_2, user_3):
        result = self._dao.user.list_(
            tenant_uuids=None, uuids=[user_2.uuid, user_3.uuid]
        )
        assert_that(result, has_items(user_2, user_3))

        result = self._dao.user.list_(tenant_uuids=None, uuids=[])
        assert_that(result, has_items(user_1, user_2, user_3))

        result = self._dao.user.list_(tenant_uuids=None, uuids=[UNKNOWN_UUID])
        assert_that(result, empty())

    @fixtures.db.user(tenant_uuid=TENANT_1)
    @fixtures.db.user(tenant_uuid=TENANT_2)
    def test_count(self, user_1, user_2):
        result = self._dao.user.count([user_1.tenant_uuid])
        assert_that(result, equal_to(1))

        result = self._dao.user.count([user_1.tenant_uuid, user_2.tenant_uuid])
        assert_that(result, equal_to(2))

    @fixtures.db.user()
    def test_update(self, user):
        user_uuid = user.uuid
        user_state = 'invisible'
        user_status = 'other status'
        user_last_activity = datetime.datetime.now(datetime.UTC)
        user_do_not_disturb = True

        user.state = user_state
        user.status = user_status
        user.last_activity = user_last_activity
        user.do_not_disturb = user_do_not_disturb
        self._dao.user.update(user)

        self._session.expire_all()
        assert_that(
            user,
            has_properties(
                uuid=user_uuid,
                state=user_state,
                status=user_status,
                last_activity=user_last_activity,
                do_not_disturb=user_do_not_disturb,
            ),
        )

    @fixtures.db.user()
    def test_add_session(self, user):
        session_uuid = uuid.uuid4()
        session = Session(uuid=session_uuid)
        self._dao.user.add_session(user, session)

        self._session.expire_all()
        assert_that(user.sessions, contains(has_properties(uuid=session_uuid)))

        # twice with same instance
        self._dao.user.add_session(user, session)

        self._session.expire_all()
        assert_that(user.sessions, contains(has_properties(uuid=session_uuid)))

        # twice with different instances
        session = Session(uuid=session_uuid)
        self._dao.user.add_session(user, session)

        self._session.expire_all()
        assert_that(user.sessions, contains(has_properties(uuid=session_uuid)))

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.session(user_uuid=USER_UUID)
    def test_remove_session(self, user, session):
        self._dao.user.remove_session(user, session)

        self._session.expire_all()
        assert_that(user.sessions, empty())

        # twice
        self._dao.user.remove_session(user, session)

        self._session.expire_all()
        assert_that(user.sessions, empty())

    @fixtures.db.user()
    def test_add_refresh_token(self, user):
        token_client_id = 'my-client-id'
        token = RefreshToken(client_id=token_client_id)
        self._dao.user.add_refresh_token(user, token)

        self._session.expire_all()
        assert_that(
            user.refresh_tokens, contains(has_properties(client_id=token_client_id))
        )

        # twice with same instance
        self._dao.user.add_refresh_token(user, token)

        self._session.expire_all()
        assert_that(
            user.refresh_tokens, contains(has_properties(client_id=token_client_id))
        )

        # twice with different instances
        token = RefreshToken(client_id=token_client_id)
        self._dao.user.add_refresh_token(user, token)

        self._session.expire_all()
        assert_that(
            user.refresh_tokens, contains(has_properties(client_id=token_client_id))
        )

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.refresh_token(user_uuid=USER_UUID)
    def test_remove_refresh_token(self, user, token):
        self._dao.user.remove_refresh_token(user, token)

        self._session.expire_all()
        assert_that(user.refresh_tokens, empty())

        # twice
        self._dao.user.remove_refresh_token(user, token)

        self._session.expire_all()
        assert_that(user.refresh_tokens, empty())

    @fixtures.db.user()
    def test_add_line(self, user):
        line_id = random.randint(1, 1000000)
        line = Line(id=line_id)
        self._dao.user.add_line(user, line)

        self._session.expire_all()
        assert_that(user.lines, contains(has_properties(id=line_id)))

        # twice
        self._dao.user.add_line(user, line)

        self._session.expire_all()
        assert_that(user.lines, contains(has_properties(id=line_id)))

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.line(user_uuid=USER_UUID)
    def test_remove_line(self, user, line):
        self._dao.user.remove_line(user, line)

        self._session.expire_all()
        assert_that(user.lines, empty())

        # twice
        self._dao.user.remove_line(user, line)

        self._session.expire_all()
        assert_that(user.lines, empty())
