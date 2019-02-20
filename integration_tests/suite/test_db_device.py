# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    equal_to,
    has_items,
    has_properties,
)
from sqlalchemy.inspection import inspect

from wazo_chatd.database.models import Device
from wazo_chatd.exceptions import UnknownDeviceException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy

TENANT_UUID = str(uuid.uuid4())
USER_UUID = str(uuid.uuid4())
UNKNOWN_NAME = 'unknown'


class TestDevice(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    def test_create(self):
        device_name = 'PJSIP/name'
        device = Device(
            name=device_name,
        )
        device = self._dao.device.create(device)

        self._session.expire_all()
        assert_that(inspect(device).persistent)
        assert_that(device, has_properties(
            name=device_name,
            state='unavailable',
        ))

    @fixtures.db.device()
    @fixtures.db.device(name='name')
    def test_get_by(self, device, _):
        result = self._dao.device.get_by(name=device.name)
        assert_that(result, equal_to(device))

        assert_that(
            calling(self._dao.device.get_by).with_args(name=UNKNOWN_NAME),
            raises(UnknownDeviceException),
        )

    @fixtures.db.device()
    @fixtures.db.device()
    def test_find_by(self, device, _):
        result = self._dao.device.find_by(name=device.name)
        assert_that(result, equal_to(device))

        result = self._dao.device.find_by(name=UNKNOWN_NAME)
        assert_that(result, equal_to(None))

    @fixtures.db.device()
    @fixtures.db.device()
    def test_list(self, device_1, device_2):
        devices = self._dao.device.list_()
        assert_that(devices, has_items(device_1, device_2))

    @fixtures.db.device(state='available')
    def test_update(self, device):
        state = 'unavailable'
        device.state = state
        self._dao.device.update(device)

        self._session.expire_all()
        assert_that(device.state, equal_to(state))

    @fixtures.db.device()
    @fixtures.db.device()
    def test_delete_all(self, device_1, device_2):
        self._dao.device.delete_all()

        assert_that(inspect(device_1).deleted)
        assert_that(inspect(device_2).deleted)
