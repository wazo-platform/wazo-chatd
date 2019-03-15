# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from hamcrest import (
    assert_that,
    calling,
    contains_inanyorder,
    equal_to,
    has_properties,
    is_not,
    none,
)

from wazo_chatd.exceptions import UnknownRoomException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import (
    BaseIntegrationTest,
    UNKNOWN_UUID,
    MASTER_TENANT_UUID as TENANT_1,
    SUBTENANT_UUID as TENANT_2,
)
from .helpers.wait_strategy import NoWaitStrategy


class TestRoom(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.room(tenant_uuid=TENANT_1)
    @fixtures.db.room(tenant_uuid=TENANT_2)
    def test_get(self, room_1, room_2):
        result = self._dao.room.get([room_1.tenant_uuid], room_1.uuid)
        assert_that(result, equal_to(room_1))

        assert_that(
            calling(self._dao.room.get).with_args([room_1.tenant_uuid], room_2.uuid),
            raises(UnknownRoomException, has_properties(status_code=404))
        )

    def test_get_doesnt_exist(self):
        assert_that(
            calling(self._dao.room.get).with_args([TENANT_1], UNKNOWN_UUID),
            raises(
                UnknownRoomException,
                has_properties(
                    status_code=404,
                    id_='unknown-room',
                    resource='rooms',
                    details=is_not(none()),
                    message=is_not(none()),
                )
            )
        )

    @fixtures.db.room(tenant_uuid=TENANT_1)
    @fixtures.db.room(tenant_uuid=TENANT_2)
    def test_list(self, room_1, room_2):
        result = self._dao.room.list_([room_1.tenant_uuid])
        assert_that(result, contains_inanyorder(room_1))

        result = self._dao.room.list_([room_1.tenant_uuid, room_2.tenant_uuid])
        assert_that(result, contains_inanyorder(room_1, room_2))

    @fixtures.db.room(tenant_uuid=TENANT_1)
    @fixtures.db.room(tenant_uuid=TENANT_2)
    def test_count(self, room_1, room_2):
        result = self._dao.room.count([room_1.tenant_uuid])
        assert_that(result, equal_to(1))

        result = self._dao.room.count([room_1.tenant_uuid, room_2.tenant_uuid])
        assert_that(result, equal_to(2))

    @fixtures.db.room(name='original')
    def test_update(self, room):
        room.name = 'updated'
        self._dao.room.update(room)

        self._session.expire_all()
        assert_that(room, has_properties(name='updated'))
