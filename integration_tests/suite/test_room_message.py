# Copyright 2019-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
from datetime import datetime

from hamcrest import (
    assert_that,
    calling,
    contains,
    contains_inanyorder,
    equal_to,
    has_entries,
    has_properties,
    is_not,
    none,
    not_,
)
from wazo_chatd_client.exceptions import ChatdError
from wazo_test_helpers.hamcrest.raises import raises
from wazo_test_helpers.hamcrest.uuid_ import uuid_

from .helpers import fixtures
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    WAZO_UUID,
    APIIntegrationTest,
    use_asset,
)

UNKNOWN_UUID = str(uuid.uuid4())
USER_1 = {'uuid': str(uuid.uuid4())}
USER_2 = {'uuid': str(uuid.uuid4())}


@use_asset('base')
class TestUserRoom(APIIntegrationTest):
    @fixtures.http.room()
    def test_list(self, room):
        message_args = {'content': 'message content'}
        message_1 = self.chatd.rooms.create_message_from_user(
            room['uuid'], message_args
        )
        message_2 = self.chatd.rooms.create_message_from_user(
            room['uuid'], message_args
        )

        messages = self.chatd.rooms.list_messages_from_user(room['uuid'])
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_2), has_entries(**message_1)),
                total=equal_to(2),
                filtered=equal_to(2),
            ),
        )

    @fixtures.http.room()
    def test_list_paginate(self, room):
        message_args = {'content': 'message content'}
        self.chatd.rooms.create_message_from_user(room['uuid'], message_args)
        message_2 = self.chatd.rooms.create_message_from_user(
            room['uuid'], message_args
        )
        self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        messages = self.chatd.rooms.list_messages_from_user(
            room['uuid'], direction='asc', offset=1, limit=1
        )
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_2)),
                total=equal_to(3),
                filtered=equal_to(3),
            ),
        )

    @fixtures.http.room()
    def test_list_search(self, room):
        message_1_args = message_2_args = {'content': 'found'}
        message_3_args = {'content': 'hidden'}
        message_1 = self.chatd.rooms.create_message_from_user(
            room['uuid'], message_1_args
        )
        message_2 = self.chatd.rooms.create_message_from_user(
            room['uuid'], message_2_args
        )
        self.chatd.rooms.create_message_from_user(room['uuid'], message_3_args)

        messages = self.chatd.rooms.list_messages_from_user(
            room['uuid'], search='found'
        )
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_2), has_entries(**message_1)),
                total=equal_to(3),
                filtered=equal_to(2),
            ),
        )

    def test_list_in_unknown_room(self):
        assert_that(
            calling(self.chatd.rooms.list_messages_from_user).with_args(UNKNOWN_UUID),
            raises(
                ChatdError, has_properties(status_code=404, error_id='unknown-room')
            ),
        )

    @fixtures.http.room(users=[USER_1, USER_2, {'uuid': str(TOKEN_USER_UUID)}])
    def test_list_when_many_users(self, room):
        assert_that(
            calling(self.chatd.rooms.list_messages_from_user).with_args(
                room_uuid=room['uuid']
            ),
            not_(raises(ChatdError, has_properties(status_code=404))),
        )

    @fixtures.http.room(users=[USER_1])
    def test_list_in_non_participant_room(self, other_room):
        with self.user_token(USER_2['uuid']):
            assert_that(
                calling(self.chatd.rooms.list_messages_from_user).with_args(
                    room_uuid=other_room['uuid']
                ),
                raises(ChatdError, has_properties(status_code=404)),
            )

    @fixtures.http.room()
    def test_create(self, room):
        message_args = {'content': 'Message content', 'alias': 'Alias'}

        message = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        assert_that(
            message,
            has_entries(
                uuid=uuid_(),
                content=message_args['content'],
                alias=message_args['alias'],
                user_uuid=str(TOKEN_USER_UUID),
                tenant_uuid=str(TOKEN_TENANT_UUID),
                wazo_uuid=str(WAZO_UUID),
                created_at=is_not(none()),
                room=has_entries(uuid=room['uuid']),
            ),
        )

    @fixtures.http.room()
    def test_create_minimal_parameters(self, room):
        message_args = {'content': 'Message content'}

        message = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        assert_that(
            message,
            has_entries(
                uuid=uuid_(),
                content=message_args['content'],
                alias=none(),
                user_uuid=str(TOKEN_USER_UUID),
                tenant_uuid=str(TOKEN_TENANT_UUID),
                wazo_uuid=str(WAZO_UUID),
                created_at=is_not(none()),
                room=has_entries(uuid=room['uuid']),
            ),
        )

    @fixtures.http.room()
    def test_create_events(self, room):
        message_args = {'content': 'Message content', 'alias': 'Alias'}
        event_accumulator = self.bus.accumulator(
            headers={
                'name': 'chatd_user_room_message_created',
                'room_uuid': room['uuid'],
            }
        )

        message = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        event = event_accumulator.accumulate(with_headers=True)
        required_acl_fmt = (
            'events.chatd.users.{user_uuid}.rooms.{room_uuid}.messages.created'
        )
        user_uuid_1 = room['users'][0]['uuid']
        user_uuid_2 = room['users'][1]['uuid']
        assert_that(
            event,
            contains_inanyorder(
                has_entries(
                    message=has_entries(
                        data=has_entries(**message),
                        required_acl=required_acl_fmt.format(
                            user_uuid=user_uuid_1, room_uuid=room['uuid']
                        ),
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                ),
                has_entries(
                    message=has_entries(
                        data=has_entries(**message),
                        required_acl=required_acl_fmt.format(
                            user_uuid=user_uuid_2, room_uuid=room['uuid']
                        ),
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                ),
            ),
        )

    def test_create_in_unknown_room(self):
        assert_that(
            calling(self.chatd.rooms.create_message_from_user).with_args(
                UNKNOWN_UUID, {}
            ),
            raises(
                ChatdError, has_properties(status_code=404, error_id='unknown-room')
            ),
        )


@use_asset('base')
class TestUserMessage(APIIntegrationTest):
    def test_list(self):
        assert_that(
            calling(self.chatd.rooms.search_messages_from_user),
            raises(
                ChatdError, has_properties(error_id='invalid-data', status_code=400)
            ),
        )

    @fixtures.http.room()
    @fixtures.http.room()
    def test_list_paginate(self, room_1, room_2):
        message_args = {'content': 'search required'}
        self.chatd.rooms.create_message_from_user(room_1['uuid'], message_args)
        message_2 = self.chatd.rooms.create_message_from_user(
            room_1['uuid'], message_args
        )
        message_3 = self.chatd.rooms.create_message_from_user(
            room_2['uuid'], message_args
        )
        self.chatd.rooms.create_message_from_user(room_2['uuid'], message_args)

        messages = self.chatd.rooms.search_messages_from_user(
            search='required', direction='asc', offset=1, limit=2
        )
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_2), has_entries(**message_3)),
                total=equal_to(4),
                filtered=equal_to(4),
            ),
        )

    @fixtures.http.room()
    @fixtures.http.room()
    def test_list_search(self, room_1, room_2):
        message_1_args = message_2_args = {'content': 'found'}
        message_3_args = {'content': 'hidden'}
        message_1 = self.chatd.rooms.create_message_from_user(
            room_1['uuid'], message_1_args
        )
        message_2 = self.chatd.rooms.create_message_from_user(
            room_2['uuid'], message_2_args
        )
        self.chatd.rooms.create_message_from_user(room_1['uuid'], message_3_args)

        messages = self.chatd.rooms.search_messages_from_user(search='found')
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_2), has_entries(**message_1)),
                total=equal_to(3),
                filtered=equal_to(2),
            ),
        )

    @fixtures.http.room()
    @fixtures.http.room()
    def test_list_distinct(self, room_1, room_2):
        message_1_args = {'content': 'hidden'}
        message_2_args = message_3_args = {'content': 'found'}
        self.chatd.rooms.create_message_from_user(room_1['uuid'], message_1_args)
        message_2 = self.chatd.rooms.create_message_from_user(
            room_2['uuid'], message_2_args
        )
        message_3 = self.chatd.rooms.create_message_from_user(
            room_1['uuid'], message_3_args
        )

        messages = self.chatd.rooms.search_messages_from_user(distinct='room_uuid')
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_3), has_entries(**message_2)),
                total=equal_to(3),
                filtered=equal_to(2),
            ),
        )

    @fixtures.http.room()
    @fixtures.http.room()
    def test_list_distinct_with_search(self, room_1, room_2):
        message_1_args = message_3_args = {'content': 'not found'}
        message_2_args = message_4_args = {'content': 'found'}
        self.chatd.rooms.create_message_from_user(room_1['uuid'], message_1_args)
        message_2 = self.chatd.rooms.create_message_from_user(
            room_1['uuid'], message_2_args
        )
        self.chatd.rooms.create_message_from_user(room_2['uuid'], message_3_args)
        message_4 = self.chatd.rooms.create_message_from_user(
            room_2['uuid'], message_4_args
        )

        messages = self.chatd.rooms.search_messages_from_user(
            distinct='room_uuid', search='found'
        )
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_4), has_entries(**message_2)),
                total=equal_to(4),
                filtered=equal_to(2),
            ),
        )

    @fixtures.http.room()
    def test_list_from_date(self, room):
        message_1_args = {"content": "msg1"}
        message_2_args = {"content": "msg2"}
        message_3_args = {"content": "msg3"}

        time_1 = datetime.utcnow().isoformat()
        message_1 = self.chatd.rooms.create_message_from_user(
            room["uuid"], message_1_args
        )
        message_2 = self.chatd.rooms.create_message_from_user(
            room["uuid"], message_2_args
        )
        time_3 = datetime.utcnow().isoformat()
        message_3 = self.chatd.rooms.create_message_from_user(
            room["uuid"], message_3_args
        )

        messages = self.chatd.rooms.list_messages_from_user(
            room["uuid"], from_date=time_1
        )
        assert_that(
            messages,
            has_entries(
                items=contains(
                    has_entries(**message_3),
                    has_entries(**message_2),
                    has_entries(**message_1),
                ),
                total=equal_to(3),
                filtered=equal_to(3),
            ),
        )

        messages = self.chatd.rooms.list_messages_from_user(
            room["uuid"], from_date=time_3
        )
        assert_that(
            messages,
            has_entries(
                items=contains(has_entries(**message_3)),
                total=equal_to(3),
                filtered=equal_to(1),
            ),
        )

    @fixtures.http.room()
    def test_list_from_invalid_date_error(self, room):
        assert_that(
            calling(self.chatd.rooms.list_messages_from_user).with_args(
                room["uuid"], from_date="invalid"
            ),
            raises(
                ChatdError, has_properties(status_code=400, error_id="invalid-data")
            ),
        )
