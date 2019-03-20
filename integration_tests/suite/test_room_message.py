# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    contains,
    equal_to,
    has_entries,
    has_properties,
    none,
    is_not,
)

from xivo_test_helpers.auth import MockUserToken
from xivo_test_helpers.hamcrest.raises import raises
from xivo_test_helpers.hamcrest.uuid_ import uuid_

from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    BaseIntegrationTest,
    WAZO_UUID,
)

TOKEN_UUID = '00000000-0000-0000-0000-000000000001'
TOKEN_TENANT_UUID = '00000000-0000-0000-0000-000000000020'
TOKEN_USER_UUID = '00000000-0000-0000-0000-000000000300'

UUID = str(uuid.uuid4())
UUID_2 = str(uuid.uuid4())
UNKNOWN_UUID = str(uuid.uuid4())


class TestUserRoom(BaseIntegrationTest):

    asset = 'base'

    # TODO move to base class
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        token = MockUserToken(
            TOKEN_UUID,
            TOKEN_USER_UUID,
            metadata={'uuid': TOKEN_USER_UUID, 'tenant_uuid': TOKEN_TENANT_UUID},
        )
        cls.auth.set_token(token)
        cls.chatd = cls.make_chatd(token=TOKEN_UUID)

    def setUp(self):
        super().setUp()
        self._dao.tenant.find_or_create(TOKEN_TENANT_UUID)
        self._session.commit()

    @fixtures.http.room()
    def test_list(self, room):
        message_args = {'content': 'message content'}
        message_1 = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)
        message_2 = self.chatd.rooms.create_message_from_user(room['uuid'], message_args)

        messages = self.chatd.rooms.list_messages_from_user(room['uuid'], direction='asc')
        assert_that(messages, has_entries(
            items=contains(has_entries(**message_1), has_entries(**message_2)),
            total=equal_to(2),
            filtered=equal_to(2),
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
            created_at=is_not(none())
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
            created_at=is_not(none())
        ))

    def test_create_in_unknown_room(self):
        assert_that(
            calling(self.chatd.rooms.create_message_from_user).with_args(UNKNOWN_UUID, {}),
            raises(ChatdError, has_properties(status_code=404, error_id='unknown-room'))
        )
