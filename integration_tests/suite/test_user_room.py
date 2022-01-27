# Copyright 2019-2021 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    contains_inanyorder,
    equal_to,
    has_entries,
    has_properties,
    none,
)

from wazo_test_helpers.hamcrest.raises import raises
from wazo_test_helpers.hamcrest.uuid_ import uuid_

from wazo_chatd.database.models import Room
from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    APIIntegrationTest,
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    WAZO_UUID,
    use_asset,
)

UUID = str(uuid.uuid4())
UUID_2 = str(uuid.uuid4())


@use_asset('base')
class TestUserRoom(APIIntegrationTest):
    @fixtures.http.room()
    @fixtures.http.room()
    @fixtures.db.room()
    def test_list(self, room_1, room_2, _):
        rooms = self.chatd.rooms.list_from_user()
        assert_that(
            rooms,
            has_entries(
                items=contains_inanyorder(
                    has_entries(
                        uuid=room_1['uuid'], users=contains_inanyorder(*room_1['users'])
                    ),
                    has_entries(
                        uuid=room_2['uuid'], users=contains_inanyorder(*room_2['users'])
                    ),
                ),
                total=equal_to(2),
                filtered=equal_to(2),
            ),
        )

    def _create_rooms(self, name, addThirdUser):
        room_args = {
            'name': name,
            'users': [
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
                {'uuid': UUID, 'tenant_uuid': UUID, 'wazo_uuid': UUID},
            ],
        }
        if (addThirdUser):
            room_args['users'].append({'uuid': UUID_2, 'tenant_uuid': UUID_2, 'wazo_uuid': UUID_2})

        routing_key = 'chatd.users.*.rooms.created'
        event_accumulator = self.bus.accumulator(routing_key)

        room = self.chatd.rooms.create_from_user(room_args)

        assert_that(
            room,
            has_entries(
                uuid=uuid_(),
                name=room_args['name'],
                users=contains_inanyorder(*room_args['users']),
            ),
        )

        event = event_accumulator.accumulate()
        assert_that(
            event,
            contains_inanyorder(
                has_entries(
                    data=has_entries(room_args),
                    required_acl=f'events.chatd.users.{TOKEN_USER_UUID}.rooms.created',
                ),
                has_entries(
                    data=has_entries(room_args),
                    required_acl=f'events.chatd.users.{UUID}.rooms.created',
                ),
                addThirdUser && has_entries(
                    data=has_entries(room_args),
                    required_acl=f'events.chatd.users.{UUID_2}.rooms.created',
                ),
            ),
        )

        self._delete_room(room)
    
    def test_create(self):
        self._create_rooms('test-room', false)
    
    def test_create_group(self):
        self._create_rooms('test-room-group', true)

    def test_create_minimal_parameters(self):
        room_args = {'users': [{'uuid': UUID}]}

        room = self.chatd.rooms.create_from_user(room_args)

        assert_that(
            room,
            has_entries(
                uuid=uuid_(),
                name=none(),
                users=contains_inanyorder(
                    has_entries(
                        uuid=str(TOKEN_USER_UUID),
                        tenant_uuid=str(TOKEN_TENANT_UUID),
                        wazo_uuid=str(WAZO_UUID),
                    ),
                    has_entries(
                        uuid=room_args['users'][0]['uuid'],
                        tenant_uuid=str(TOKEN_TENANT_UUID),
                        wazo_uuid=str(WAZO_UUID),
                    ),
                ),
            ),
        )
        self._delete_room(room)

    def _delete_room(self, room):
        self._session.query(Room).filter(Room.uuid == room['uuid']).delete()
        self._session.commit()

    def _addUserRange(self, room_args):
        for _ in range(3, 101):
            room_args['users'].append({'uuid': str(uuid.uuid4()), 'tenant_uuid': str(uuid.uuid4()), 'wazo_uuid': str(uuid.uuid4())})

        return room_args

    def test_create_with_wrong_users_number(self):
        room_args = {
            'users': [
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
                {'uuid': UUID, 'tenant_uuid': UUID, 'wazo_uuid': UUID},
                {'uuid': UUID_2, 'tenant_uuid': UUID_2, 'wazo_uuid': UUID_2},
            ]
        }
        room_args = self._addUserRange(room_args)

        self._assert_create_raise_400_users_error(room_args)

        room_args = {
            'users': [
                # Current user is automatically added to the users list
                # {'uuid': str(TOKEN_USER_UUID), 'tenant_uuid': str(TOKEN_TENANT_UUID), 'wazo_uuid': str(WAZO_UUID)},
                {'uuid': UUID, 'tenant_uuid': UUID, 'wazo_uuid': UUID},
                {'uuid': UUID_2, 'tenant_uuid': UUID_2, 'wazo_uuid': UUID_2},
            ]
        }
        room_args = self._addUserRange(room_args)

        self._assert_create_raise_400_users_error(room_args)

        room_args = {'users': []}
        self._assert_create_raise_400_users_error(room_args)

        room_args = {}
        self._assert_create_raise_400_users_error(room_args)

    def _assert_create_raise_400_users_error(self, room):
        assert_that(
            calling(self.chatd.rooms.create_from_user).with_args(room),
            raises(
                ChatdError,
                has_properties(
                    status_code=400,
                    details=has_entries(
                        users=has_entries(
                            constraint_id='length', constraint={'min': 2, 'max': 100}
                        )
                    ),
                ),
            ),
        )

    def test_create_with_same_user(self):
        room_args = {
            'users': [
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
            ]
        }
        assert_that(
            calling(self.chatd.rooms.create_from_user).with_args(room_args),
            raises(ChatdError, has_properties(status_code=400)),
        )
