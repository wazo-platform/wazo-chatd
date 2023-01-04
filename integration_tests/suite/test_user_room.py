# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    contains_inanyorder,
    empty,
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

USER_1 = {'uuid': str(uuid.uuid4())}
USER_2 = {'uuid': str(uuid.uuid4())}
USER_3 = {'uuid': str(uuid.uuid4())}


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

    @fixtures.http.room(users=[USER_1])
    @fixtures.http.room(users=[USER_2])
    @fixtures.http.room(users=[USER_1, USER_2])
    def test_list_by_user_uuid(self, room_1, room_2, room_3):
        user_uuids = [USER_1['uuid']]
        rooms = self.chatd.rooms.list_from_user(user_uuids=user_uuids)
        assert_that(
            rooms,
            has_entries(
                items=contains_inanyorder(
                    has_entries(uuid=room_1['uuid']),
                    has_entries(uuid=room_3['uuid']),
                ),
                total=equal_to(2),
                filtered=equal_to(2),
            ),
        )

        user_uuids = [str(TOKEN_USER_UUID), USER_1['uuid']]
        rooms = self.chatd.rooms.list_from_user(user_uuids=user_uuids)
        assert_that(
            rooms,
            has_entries(
                items=contains_inanyorder(
                    has_entries(uuid=room_1['uuid']),
                    has_entries(uuid=room_3['uuid']),
                ),
                total=equal_to(2),
                filtered=equal_to(2),
            ),
        )

        user_uuids = [str(TOKEN_USER_UUID), USER_1['uuid'], USER_2['uuid']]
        rooms = self.chatd.rooms.list_from_user(user_uuids=user_uuids)
        assert_that(
            rooms,
            has_entries(
                items=contains_inanyorder(
                    has_entries(uuid=room_3['uuid']),
                ),
                total=equal_to(1),
                filtered=equal_to(1),
            ),
        )

        user_uuids = [str(TOKEN_USER_UUID), USER_1['uuid'], USER_3['uuid']]
        rooms = self.chatd.rooms.list_from_user(user_uuids=user_uuids)
        assert_that(
            rooms,
            has_entries(
                items=empty(),
                total=equal_to(0),
                filtered=equal_to(0),
            ),
        )

    def test_create(self):
        room_args = {
            'name': 'test-room',
            'users': [
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
                {'uuid': UUID, 'tenant_uuid': UUID, 'wazo_uuid': UUID},
            ],
        }
        headers = {'name': 'chatd_user_room_created'}
        event_accumulator = self.bus.accumulator(headers=headers)

        room = self.chatd.rooms.create_from_user(room_args)

        assert_that(
            room,
            has_entries(
                uuid=uuid_(),
                name=room_args['name'],
                users=contains_inanyorder(*room_args['users']),
            ),
        )

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains_inanyorder(
                has_entries(
                    message=has_entries(
                        data=has_entries(room_args),
                        required_acl=f'events.chatd.users.{TOKEN_USER_UUID}.rooms.created',
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                ),
                has_entries(
                    message=has_entries(
                        data=has_entries(room_args),
                        required_acl=f'events.chatd.users.{UUID}.rooms.created',
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                ),
            ),
        )
        self._delete_room(room)

    def test_create_with_many_users(self):
        room_args = {
            'name': 'test-group-room',
            'users': [
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
                {'uuid': UUID, 'tenant_uuid': UUID, 'wazo_uuid': UUID},
                {'uuid': UUID_2, 'tenant_uuid': UUID_2, 'wazo_uuid': UUID_2},
            ],
        }
        headers = {'name': 'chatd_user_room_created'}
        event_accumulator = self.bus.accumulator(headers=headers)

        room = self.chatd.rooms.create_from_user(room_args)

        assert_that(
            room,
            has_entries(
                uuid=uuid_(),
                name=room_args['name'],
                users=contains_inanyorder(*room_args['users']),
            ),
        )

        event = event_accumulator.accumulate(with_headers=True)
        expected_entries = [
            has_entries(
                message=has_entries(
                    data=has_entries(room_args),
                    required_acl=f'events.chatd.users.{uuid}.rooms.created',
                ),
                headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
            )
            for uuid in (TOKEN_USER_UUID, UUID, UUID_2)
        ]
        assert_that(event, contains_inanyorder(*expected_entries))

        self._delete_room(room)

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

    @fixtures.http.room(name='old')
    def test_create_when_already_exists(self, existing_room):
        room_args = {
            'name': 'ignored',
            'users': existing_room['users'],
        }
        room = self.chatd.rooms.create_from_user(room_args)

        assert_that(
            room,
            has_entries(
                uuid=existing_room['uuid'],
                name=existing_room['name'],
                users=existing_room['users'],
            ),
        )

    def _delete_room(self, room):
        self._session.query(Room).filter(Room.uuid == room['uuid']).delete()
        self._session.commit()

    def test_create_with_wrong_users_number(self):
        # 100 + current user = 101
        room_args = {
            'users': [
                {
                    'uuid': str(TOKEN_USER_UUID),
                    'tenant_uuid': str(TOKEN_TENANT_UUID),
                    'wazo_uuid': str(WAZO_UUID),
                },
            ]
            + self._generate_users(100)
        }
        self._assert_create_raise_400_users_error(room_args)

        # 100 without current user = 101
        room_args = {'users': self._generate_users(100)}
        self._assert_create_raise_400_users_error(room_args)

        room_args = {'users': []}
        self._assert_create_raise_400_users_error(room_args)

        room_args = {}
        self._assert_create_raise_400_users_error(room_args)

    def _generate_users(self, number):
        return [
            {
                'uuid': str(uuid.uuid4()),
                'tenant_uuid': str(uuid.uuid4()),
                'wazo_uuid': str(uuid.uuid4()),
            }
            for _ in range(number)
        ]

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
