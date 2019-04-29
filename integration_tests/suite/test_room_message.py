# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    contains,
    contains_inanyorder,
    equal_to,
    has_entries,
    has_properties,
    none,
    is_not,
)

from xivo_test_helpers.hamcrest.raises import raises
from xivo_test_helpers.hamcrest.uuid_ import uuid_

from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    BaseIntegrationTest,
    WAZO_UUID,
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
)

UUID = str(uuid.uuid4())
UUID_2 = str(uuid.uuid4())
UNKNOWN_UUID = str(uuid.uuid4())


class TestUserRoom(BaseIntegrationTest):

    asset = 'base'

    @fixtures.http.room()
    def test_list(self, room):
        message_args = {'content': 'message content'}
        message_1 = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)
        message_2 = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)
        self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        messages = self.chatd.rooms.list_messages_from_user(room['uuid'], direction='asc', limit=2)
        assert_that(messages, has_entries(
            items=contains(has_entries(**message_1), has_entries(**message_2)),
            total=equal_to(3),
            filtered=equal_to(3),
        ))

    def test_list_in_unknown_room(self):
        assert_that(
            calling(self.chatd.rooms.list_messages_from_user).with_args(UNKNOWN_UUID),
            raises(ChatdError, has_properties(status_code=404, error_id='unknown-room'))
        )

    @fixtures.http.room()
    def test_create(self, room):
        message_args = {'content': 'Message content', 'alias': 'Alias'}

        message = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        assert_that(message, has_entries(
            uuid=uuid_(),
            content=message_args['content'],
            alias=message_args['alias'],
            user_uuid=TOKEN_USER_UUID,
            tenant_uuid=TOKEN_TENANT_UUID,
            wazo_uuid=WAZO_UUID,
            created_at=is_not(none()),

            room=has_entries(uuid=room['uuid']),
        ))

    @fixtures.http.room()
    def test_create_minimal_parameters(self, room):
        message_args = {'content': 'Message content'}

        message = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        assert_that(message, has_entries(
            uuid=uuid_(),
            content=message_args['content'],
            alias=none(),
            user_uuid=TOKEN_USER_UUID,
            tenant_uuid=TOKEN_TENANT_UUID,
            wazo_uuid=WAZO_UUID,
            created_at=is_not(none()),

            room=has_entries(uuid=room['uuid']),
        ))

    @fixtures.http.room()
    def test_create_events(self, room):
        message_args = {
            'content': 'Message content',
            'alias': 'Alias',
        }
        routing_key = 'chatd.users.*.rooms.*.messages.created'
        event_accumulator = self.bus.accumulator(routing_key)

        message = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        event = event_accumulator.accumulate()
        required_acl_fmt = 'events.chatd.users.{user_uuid}.rooms.{room_uuid}.messages.created'
        user_uuid_1 = room['users'][0]['uuid']
        user_uuid_2 = room['users'][1]['uuid']
        assert_that(event, contains_inanyorder(
            has_entries(
                data=has_entries(**message),
                required_acl=required_acl_fmt.format(user_uuid=user_uuid_1, room_uuid=room['uuid']),
            ),
            has_entries(
                data=has_entries(**message),
                required_acl=required_acl_fmt.format(user_uuid=user_uuid_2, room_uuid=room['uuid']),
            ),
        ))

    def test_create_in_unknown_room(self):
        assert_that(
            calling(self.chatd.rooms.create_message_from_user).with_args(UNKNOWN_UUID, {}),
            raises(ChatdError, has_properties(status_code=404, error_id='unknown-room'))
        )
