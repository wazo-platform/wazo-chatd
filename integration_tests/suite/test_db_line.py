# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    equal_to,
    has_items,
)

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
        line = self._dao.line.get(line.id)
        assert_that(line, equal_to(line))

        assert_that(
            calling(self._dao.line.get).with_args(UNKNOWN_ID),
            raises(UnknownLineException),
        )

    @fixtures.db.line()
    @fixtures.db.line(device_name='name')
    def test_get_by(self, line, _):
        line = self._dao.line.get_by(device_name=line.device_name)
        assert_that(line, equal_to(line))

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

    @fixtures.db.line(device_name='SIP/abcd')
    def test_update(self, line):
        device_name = 'SCCP/efgh'
        line.device_name = device_name
        self._dao.line.update(line)

        self._session.expire_all()
        assert_that(line.device_name, equal_to(device_name))

    @fixtures.db.device()
    @fixtures.db.line()
    def test_associate_device(self, device, line):
        self._dao.line.associate_device(line, device)

        self._session.expire_all()
        assert_that(line.device, equal_to(device))

    @fixtures.db.device(name='device-name')
    @fixtures.db.line(device_name='device-name')
    def test_dissociate_device(self, device, line):
        self._dao.line.dissociate_device(line, device)

        self._session.expire_all()
        assert_that(line.device, equal_to(None))
