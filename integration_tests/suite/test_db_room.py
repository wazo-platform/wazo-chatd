# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime
import uuid
from typing import TYPE_CHECKING

from hamcrest import (
    assert_that,
    calling,
    contains_exactly,
    contains_inanyorder,
    empty,
    equal_to,
    has_properties,
    instance_of,
    is_not,
    none,
)
from sqlalchemy.inspection import inspect
from wazo_test_helpers.hamcrest.raises import raises

if TYPE_CHECKING:
    # NOTE(clanglois): this can be removed with sqlalchemy 2.0,
    #  as inspect should be typed correctly
    from sqlalchemy_stubs import InstanceState

from wazo_chatd.database.models import Room, RoomMessage, RoomUser
from wazo_chatd.exceptions import UnknownRoomException

from .helpers import fixtures
from .helpers.base import TOKEN_SUBTENANT_UUID as TENANT_2
from .helpers.base import TOKEN_TENANT_UUID as TENANT_1
from .helpers.base import UNKNOWN_UUID, DBIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()
USER_UUID_2 = uuid.uuid4()
USER_UUID_3 = uuid.uuid4()

UUID = uuid.uuid4()


@use_asset('database')
class TestRoom(DBIntegrationTest):
    @fixtures.db.room(tenant_uuid=TENANT_1)
    @fixtures.db.room(tenant_uuid=TENANT_2)
    def test_get(self, room_1, room_2):
        result = self._dao.room.get([room_1.tenant_uuid], room_1.uuid)
        assert_that(result, equal_to(room_1))

        assert_that(
            calling(self._dao.room.get).with_args([room_1.tenant_uuid], room_2.uuid),
            raises(UnknownRoomException, has_properties(status_code=404)),
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
                ),
            ),
        )

    @fixtures.db.room(tenant_uuid=TENANT_1)
    @fixtures.db.room(tenant_uuid=TENANT_2)
    def test_list(self, room_1, room_2):
        result = self._dao.room.list_([room_1.tenant_uuid])
        assert_that(result, contains_inanyorder(room_1))

        result = self._dao.room.list_([room_1.tenant_uuid, room_2.tenant_uuid])
        assert_that(result, contains_inanyorder(room_1, room_2))

    @fixtures.db.room(users=[{'uuid': USER_UUID_1}, {'uuid': USER_UUID_2}])
    @fixtures.db.room(users=[{'uuid': USER_UUID_1}, {'uuid': USER_UUID_3}])
    @fixtures.db.room(users=[{'uuid': USER_UUID_1}, {'uuid': USER_UUID_2}, {'uuid': USER_UUID_3}])  # fmt: skip
    @fixtures.db.room(users=[{'uuid': USER_UUID_2}, {'uuid': USER_UUID_3}])
    def test_list_by_user_uuids(self, room_1, room_2, room_3, _):
        user_uuids = [USER_UUID_1]
        result = self._dao.room.list_([room_1.tenant_uuid], user_uuids=user_uuids)
        assert_that(result, contains_inanyorder(room_1, room_2, room_3))

        user_uuids = [USER_UUID_1, USER_UUID_3]
        result = self._dao.room.list_([room_1.tenant_uuid], user_uuids=user_uuids)
        assert_that(result, contains_inanyorder(room_2, room_3))

    @fixtures.db.room(tenant_uuid=TENANT_1)
    @fixtures.db.room(tenant_uuid=TENANT_2)
    def test_count(self, room_1, room_2):
        result = self._dao.room.count([room_1.tenant_uuid])
        assert_that(result, equal_to(1))

        result = self._dao.room.count([room_1.tenant_uuid, room_2.tenant_uuid])
        assert_that(result, equal_to(2))

    @fixtures.db.room(users=[{'uuid': USER_UUID_1}, {'uuid': USER_UUID_2}])
    @fixtures.db.room(users=[{'uuid': USER_UUID_1}, {'uuid': USER_UUID_3}])
    @fixtures.db.room(users=[{'uuid': USER_UUID_1}, {'uuid': USER_UUID_2}, {'uuid': USER_UUID_3}])  # fmt: skip
    @fixtures.db.room(users=[{'uuid': USER_UUID_2}, {'uuid': USER_UUID_3}])
    def test_count_by_user_uuids(self, room_1, *_):
        user_uuids = [USER_UUID_1]
        result = self._dao.room.count([room_1.tenant_uuid], user_uuids=user_uuids)
        assert_that(result, equal_to(3))

        user_uuids = [USER_UUID_1, USER_UUID_3]
        result = self._dao.room.count([room_1.tenant_uuid], user_uuids=user_uuids)
        assert_that(result, equal_to(2))

    def test_create(self):
        room = Room(tenant_uuid=TENANT_1)
        room = self._dao.room.create(room)

        self._session.expire_all()
        assert_that(room, has_properties(uuid=instance_of(uuid.UUID)))

    def test_create_with_users(self):
        room_user = RoomUser(uuid=USER_UUID_1, tenant_uuid=UUID, wazo_uuid=UUID)
        room = Room(tenant_uuid=TENANT_1, users=[room_user])
        room = self._dao.room.create(room)

        self._session.expire_all()
        assert_that(room, has_properties(uuid=instance_of(uuid.UUID)))

    @fixtures.db.room(users=[{'uuid': USER_UUID_1}])
    def test_delete_cascade(self, room):
        self._session.query(Room).filter(Room.uuid == room.uuid).delete()

        self._session.expire_all()
        assert_that(inspect(room).deleted)

        result = (
            self._session.query(RoomUser).filter(RoomUser.uuid == USER_UUID_1).first()
        )
        assert_that(result, none())

    @fixtures.db.room()
    def test_add_message(self, room):
        message = RoomMessage(user_uuid=UUID, tenant_uuid=UUID, wazo_uuid=UUID)

        self._dao.room.add_message(room, message)

        self._session.expire_all()
        inspect_result: InstanceState = inspect(message)
        assert_that(inspect_result.persistent)
        assert_that(room.messages, contains_exactly(message))

    @fixtures.db.room(messages=[{'content': 'older'}, {'content': 'newer'}])
    def test_list_messages(self, room):
        message_2, message_1 = room.messages

        messages = self._dao.room.list_messages(room)

        assert_that(messages, contains_exactly(message_2, message_1))

    @fixtures.db.room(messages=[{'content': 'older'}, {'content': 'newer'}])
    def test_list_messages_direction(self, room):
        message_2, message_1 = room.messages

        messages = self._dao.room.list_messages(room, direction='desc')
        assert_that(messages, contains_exactly(message_2, message_1))

        messages = self._dao.room.list_messages(room, direction='asc')
        assert_that(messages, contains_exactly(message_1, message_2))

    @fixtures.db.room(messages=[{'content': 'older'}, {'content': 'newer'}])
    def test_list_messages_limit(self, room):
        message_2, message_1 = room.messages

        messages = self._dao.room.list_messages(room, limit=1)

        assert_that(messages, contains_exactly(message_2))

    @fixtures.db.room(messages=[{'content': 'older'}, {'content': 'newer'}])
    def test_list_messages_offset(self, room):
        message_2, message_1 = room.messages

        messages = self._dao.room.list_messages(room, offset=1)

        assert_that(messages, contains_exactly(message_1))

    @fixtures.db.room(messages=[{'content': 'older'}, {'content': 'newer'}])
    def test_count_messages(self, room):
        count = self._dao.room.count_messages(room)

        assert_that(count, equal_to(2))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'newer'}],
    )
    def test_list_user_messages(self, room_1, room_2):
        message_1, message_2 = room_1.messages[0], room_2.messages[0]

        messages = self._dao.room.list_user_messages(UUID, USER_UUID_1)

        assert_that(messages, contains_exactly(message_2, message_1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'newer'}],
    )
    def test_list_user_messages_direction(self, room_1, room_2):
        message_1, message_2 = room_1.messages[0], room_2.messages[0]

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, direction='desc'
        )
        assert_that(messages, contains_exactly(message_2, message_1))

        messages = self._dao.room.list_user_messages(UUID, USER_UUID_1, direction='asc')
        assert_that(messages, contains_exactly(message_1, message_2))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'newer'}],
    )
    def test_list_user_messages_limit(self, room_1, room_2):
        message_2 = room_2.messages[0]

        messages = self._dao.room.list_user_messages(UUID, USER_UUID_1, limit=1)

        assert_that(messages, contains_exactly(message_2))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'newer'}],
    )
    def test_list_user_messages_offset(self, room_1, room_2):
        message_1 = room_1.messages[0]

        messages = self._dao.room.list_user_messages(UUID, USER_UUID_1, offset=1)

        assert_that(messages, contains_exactly(message_1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'hidden'}, {'content': 'found'}],
    )
    def test_list_user_messages_search(self, room):
        message_found, _ = room.messages

        messages = self._dao.room.list_user_messages(UUID, USER_UUID_1, search='found')

        assert_that(messages, contains_exactly(message_found))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'hidden'}, {'content': 'found with space'}],
    )
    def test_list_user_messages_search_with_space(self, room):
        message_found, _ = room.messages

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, search='found space'
        )

        assert_that(messages, contains_exactly(message_found))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'hidden'}, {'content': 'fòund with accent'}],
    )
    def test_list_user_messages_search_with_accent(self, room):
        message_found, _ = room.messages

        messages = self._dao.room.list_user_messages(UUID, USER_UUID_1, search='found')

        assert_that(messages, contains_exactly(message_found))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[
            {'content': 'msg1', 'created_at': datetime.datetime(2019, 12, 31, 14, 20)},
            {'content': 'msg2', 'created_at': datetime.datetime(2019, 12, 31, 14, 15)},
            {'content': 'msg3', 'created_at': datetime.datetime(2019, 12, 31, 14, 10)},
        ],
    )
    def test_list_user_messages_from_date(self, room):
        message_1 = room.messages[0]  # 14:20
        message_2 = room.messages[1]  # 14:15
        message_3 = room.messages[2]  # 14:10

        from_date = datetime.datetime(2019, 12, 31, 14, 10)
        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, from_date=from_date
        )
        assert_that(messages, contains_exactly(message_1, message_2, message_3))

        from_date = datetime.datetime(
            2019,
            12,
            31,
            8,
            15,
            1,
            tzinfo=datetime.timezone(datetime.timedelta(hours=-6)),
        )
        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, from_date=from_date
        )
        assert_that(messages, contains_exactly(message_1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'newer'}],
    )
    def test_count_user_messages(self, *_):
        count = self._dao.room.count_user_messages(UUID, USER_UUID_1)

        assert_that(count, equal_to(2))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'hidden'}, {'content': 'found'}],
    )
    def test_count_user_messages_with_search(self, *_):
        count = self._dao.room.count_user_messages(UUID, USER_UUID_1, search='found')

        assert_that(count, equal_to(1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older1'}, {'content': 'newer1'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older2'}, {'content': 'newer2'}],
    )
    def test_list_latest_user_messages(self, room_1, room_2):
        message_1, message_2 = room_1.messages[0], room_2.messages[0]

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid'
        )
        assert_that(messages, contains_exactly(message_2, message_1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older1'}, {'content': 'newer1'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older2'}, {'content': 'newer2'}],
    )
    def test_list_latest_user_messages_direction(self, room_1, room_2):
        message_1, message_2 = room_1.messages[0], room_2.messages[0]

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid', direction='desc'
        )
        assert_that(messages, contains_exactly(message_2, message_1))

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid', direction='asc'
        )
        assert_that(messages, contains_exactly(message_1, message_2))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older1'}, {'content': 'newer1'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older2'}, {'content': 'newer2'}],
    )
    def test_list_latest_user_messages_limit(self, room_1, room_2):
        message_2 = room_2.messages[0]

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid', limit=1
        )

        assert_that(messages, contains_exactly(message_2))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older1'}, {'content': 'newer1'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'older2'}, {'content': 'newer2'}],
    )
    def test_list_latest_user_messages_offset(self, room_1, room_2):
        message_1 = room_1.messages[0]

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid', offset=1
        )

        assert_that(messages, contains_exactly(message_1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'not found'}, {'content': 'found'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'not found'}, {'content': 'hidden'}],
    )
    def test_list_latest_user_messages_search(self, room_1, room_2):
        message_1 = room_1.messages[0]

        messages = self._dao.room.list_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid', search='found'
        )

        assert_that(messages, contains_exactly(message_1))

    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'not found'}, {'content': 'found'}],
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1, 'tenant_uuid': UUID}],
        messages=[{'content': 'not found'}, {'content': 'hidden'}],
    )
    def test_count_latest_user_messages_with_search(self, *_):
        count = self._dao.room.count_user_messages(
            UUID, USER_UUID_1, distinct='room_uuid', search='found'
        )

        assert_that(count, equal_to(1))


@use_asset('database')
class TestRoomRelationships(DBIntegrationTest):
    @fixtures.db.room()
    def test_users_create(self, room):
        room_user = RoomUser(uuid=USER_UUID_1, tenant_uuid=UUID, wazo_uuid=UUID)
        room.users = [room_user]
        self._session.flush()

        self._session.expire_all()
        inspect_result: InstanceState = inspect(room_user)
        assert_that(inspect_result.persistent)
        assert_that(room.users, contains_exactly(room_user))

    @fixtures.db.room(users=[{'uuid': USER_UUID_1}])
    def test_users_delete(self, room):
        room_user = room.users[0]
        room.users = []
        self._session.flush()

        self._session.expire_all()
        assert_that(inspect(room_user).deleted)
        assert_that(room.users, empty())

    @fixtures.db.room()
    def test_users_get(self, room):
        room_user = RoomUser(
            room_uuid=room.uuid, uuid=USER_UUID_1, tenant_uuid=UUID, wazo_uuid=UUID
        )
        self._session.add(room_user)
        self._session.flush()

        self._session.expire_all()
        assert_that(room.users, contains_exactly(room_user))

    @fixtures.db.room()
    def test_messages_create(self, room):
        message = RoomMessage(user_uuid=UUID, tenant_uuid=UUID, wazo_uuid=UUID)
        room.messages = [message]
        self._session.flush()

        self._session.expire_all()
        inspect_result: InstanceState = inspect(message)
        assert_that(inspect_result.persistent)
        assert_that(room.messages, contains_exactly(message))

    @fixtures.db.room()
    def test_messages_delete(self, room):
        message = RoomMessage(user_uuid=UUID, tenant_uuid=UUID, wazo_uuid=UUID)
        room.messages = [message]
        self._session.flush()

        room.messages = []
        self._session.flush()

        self._session.expire_all()
        inspect_result: InstanceState = inspect(message)
        assert_that(inspect_result.deleted)
        assert_that(room.messages, empty())

    @fixtures.db.room()
    def test_messages_get(self, room):
        now = datetime.datetime.utcnow()
        yesterday = now - datetime.timedelta(days=1)
        message_1 = self.add_room_message(room_uuid=room.uuid, created_at=yesterday)
        message_2 = self.add_room_message(room_uuid=room.uuid, created_at=now)

        self._session.expire_all()
        assert_that(room.messages, contains_exactly(message_2, message_1))

    def add_room_message(self, **kwargs):
        kwargs.setdefault('user_uuid', uuid.uuid4())
        kwargs.setdefault('tenant_uuid', uuid.uuid4())
        kwargs.setdefault('wazo_uuid', uuid.uuid4())
        message = RoomMessage(**kwargs)
        self._session.add(message)
        self._session.flush()
        return message


@use_asset('database')
class TestRoomMessageRelationships(DBIntegrationTest):
    @fixtures.db.room(messages=[{'content': 'msg1'}])
    def test_room_get(self, room):
        message = room.messages[0]

        self._session.expire_all()
        assert_that(message.room, equal_to(room))
