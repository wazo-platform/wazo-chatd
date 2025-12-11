# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import TYPE_CHECKING

from hamcrest import assert_that, calling, equal_to, has_properties
from sqlalchemy.inspection import inspect
from wazo_test_helpers.hamcrest.raises import raises

if TYPE_CHECKING:
    # NOTE(clanglois): this can be removed with sqlalchemy 2.0,
    #  as inspect should be typed correctly
    from sqlalchemy_stubs import InstanceState

from wazo_chatd.database.models import Endpoint
from wazo_chatd.exceptions import UnknownEndpointException

from .helpers import fixtures
from .helpers.base import DBIntegrationTest, use_asset

UNKNOWN_NAME = 'unknown'


@use_asset('database')
class TestEndpoint(DBIntegrationTest):
    def test_create(self):
        endpoint_name = 'PJSIP/name'
        endpoint = Endpoint(name=endpoint_name)
        endpoint = self._dao.endpoint.create(endpoint)

        self._session.expire_all()
        inspect_result: InstanceState = inspect(endpoint)
        assert_that(inspect_result.persistent)
        assert_that(endpoint, has_properties(name=endpoint_name, state='unavailable'))

        self._dao.endpoint.delete_all()

    def test_find_or_create(self):
        endpoint_name = 'PJSIP/name'
        created_endpoint = self._dao.endpoint.find_or_create(endpoint_name)

        self._session.expire_all()
        assert_that(inspect(created_endpoint).persistent)
        assert_that(created_endpoint, has_properties(name=endpoint_name))

        found_endpoint = self._dao.endpoint.find_or_create(created_endpoint.name)
        assert_that(found_endpoint, has_properties(name=created_endpoint.name))

        self._dao.endpoint.delete_all()

    @fixtures.db.endpoint()
    @fixtures.db.endpoint(name='name')
    def test_get_by(self, endpoint, _):
        result = self._dao.endpoint.get_by(name=endpoint.name)
        assert_that(result, equal_to(endpoint))

        assert_that(
            calling(self._dao.endpoint.get_by).with_args(name=UNKNOWN_NAME),
            raises(UnknownEndpointException),
        )

    @fixtures.db.endpoint()
    @fixtures.db.endpoint()
    def test_find_by(self, endpoint, _):
        result = self._dao.endpoint.find_by(name=endpoint.name)
        assert_that(result, equal_to(endpoint))

        result = self._dao.endpoint.find_by(name=UNKNOWN_NAME)
        assert_that(result, equal_to(None))

    @fixtures.db.endpoint(state='available')
    def test_update(self, endpoint):
        state = 'unavailable'
        endpoint.state = state
        self._dao.endpoint.update(endpoint)

        self._session.expire_all()
        assert_that(endpoint.state, equal_to(state))

    @fixtures.db.endpoint()
    @fixtures.db.endpoint()
    def test_delete_all(self, endpoint_1, endpoint_2):
        self._session.refresh(endpoint_1)
        self._session.refresh(endpoint_2)
        self._dao.endpoint.delete_all()

        assert_that(inspect(endpoint_1).deleted)
        assert_that(inspect(endpoint_2).deleted)
