# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import assert_that, calling, equal_to, has_items

from wazo_chatd.exceptions import UnknownLineException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy

TENANT_UUID = str(uuid.uuid4())
USER_UUID = str(uuid.uuid4())
UNKNOWN_ID = 0


class TestLine(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.line()
    def test_get(self, line):
        result = self._dao.line.get(line.id)
        assert_that(result, equal_to(line))

        assert_that(
            calling(self._dao.line.get).with_args(UNKNOWN_ID),
            raises(UnknownLineException),
        )

    @fixtures.db.line()
    @fixtures.db.line()
    def test_find(self, line, _):
        result = self._dao.line.find(line.id)
        assert_that(result, equal_to(line))

        result = self._dao.line.find(UNKNOWN_ID)
        assert_that(result, equal_to(None))

    @fixtures.db.line()
    @fixtures.db.line()
    def test_list(self, line_1, line_2):
        lines = self._dao.line.list_()
        assert_that(lines, has_items(line_1, line_2))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TENANT_UUID)
    @fixtures.db.line(user_uuid=USER_UUID)
    def test_tenant_uuid(self, tenant, _, line):
        assert_that(line.tenant_uuid, equal_to(tenant.uuid))

    @fixtures.db.endpoint(name='SIP/custom-name')
    @fixtures.db.line(endpoint_name='SIP/custom-name')
    def test_state(self, endpoint, line):
        assert_that(line.state, equal_to(endpoint.state))

    @fixtures.db.line(media='audio')
    def test_update(self, line):
        line.media = 'video'
        self._dao.line.update(line)

        self._session.expire_all()
        assert_that(line.media, equal_to('video'))

    @fixtures.db.endpoint()
    @fixtures.db.line()
    def test_associate_endpoint(self, endpoint, line):
        self._dao.line.associate_endpoint(line, endpoint)

        self._session.expire_all()
        assert_that(line.endpoint, equal_to(endpoint))

    @fixtures.db.endpoint(name='endpoint-name')
    @fixtures.db.line(endpoint_name='endpoint-name')
    def test_dissociate_endpoint(self, endpoint, line):
        self._dao.line.dissociate_endpoint(line)

        self._session.expire_all()
        assert_that(line.endpoint, equal_to(None))
