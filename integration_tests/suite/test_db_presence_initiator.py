# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
from unittest.mock import Mock

from hamcrest import assert_that, equal_to, has_properties

from wazo_chatd.plugins.presences.initiator import Initiator

from .helpers import fixtures
from .helpers.base import DBIntegrationTest, use_asset

TENANT_UUID = uuid.uuid4()
USER_UUID = uuid.uuid4()
LINE_ID = 42
ENDPOINT_NAME = 'PJSIP/12345'


@use_asset('database')
class TestDBPresenceInitiator(DBIntegrationTest):
    def setUp(self):
        super().setUp()
        self.initiator = Initiator(self._dao, Mock, Mock, Mock)

    @fixtures.db.tenant(uuid=TENANT_UUID)
    def test_initiate_session_when_no_user_associate(self, tenant):
        session_uuid = uuid.uuid4()
        sessions = [
            {
                'uuid': str(session_uuid),
                'user_uuid': str(USER_UUID),
                'tenant_uuid': str(TENANT_UUID),
            }
        ]

        self.initiator.initiate_sessions(sessions)

        result = self._dao.session.find(session_uuid)
        assert_that(result, equal_to(None))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    def test_initiate_refresh_token_when_no_user_associate(self, tenant):
        client_id = 'my-client-id'
        refresh_tokens = [
            {
                'client_id': client_id,
                'user_uuid': str(USER_UUID),
                'tenant_uuid': str(TENANT_UUID),
            }
        ]

        self.initiator.initiate_refresh_tokens(refresh_tokens)

        result = self._dao.refresh_token.find(USER_UUID, client_id)
        assert_that(result, equal_to(None))

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.endpoint(name=ENDPOINT_NAME)
    @fixtures.db.line(id=LINE_ID, user_uuid=USER_UUID, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(name=f'{ENDPOINT_NAME}-abcd', line_id=LINE_ID)
    def test_initiate_channels_when_channel_is_hold(
        self, user, endpoint, line, channel
    ):
        events = [
            {
                'Event': 'CoreShowChannel',
                'Channel': channel.name,
                'ChannelStateDesc': 'Up',
                'ChanVariable': {'XIVO_ON_HOLD': '1'},
            }
        ]

        self.initiator.initiate_channels(events)

        result = self._dao.channel.find(channel.name)
        assert_that(result, has_properties(name=channel.name, state='holding'))

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.endpoint(name=ENDPOINT_NAME)
    @fixtures.db.line(id=LINE_ID, user_uuid=USER_UUID, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(name=f'{ENDPOINT_NAME}-abcd', line_id=LINE_ID)
    def test_initiate_channels_when_channel_is_unhold(
        self, user, endpoint, line, channel
    ):
        events = [
            {
                'Event': 'CoreShowChannel',
                'Channel': channel.name,
                'ChannelStateDesc': 'Up',
                'ChanVariable': {'XIVO_ON_HOLD': ''},
            }
        ]

        self.initiator.initiate_channels(events)

        result = self._dao.channel.find(channel.name)
        assert_that(result, has_properties(name=channel.name, state='talking'))

    def test_initiate_channels_when_no_line_associate(self):
        channel_name = 'PJSIP/unknown-channel'
        events = [
            {
                'Event': 'CoreShowChannel',
                'Channel': channel_name,
                'ChannelStateDesc': 'Up',
            }
        ]

        self.initiator.initiate_channels(events)

        result = self._dao.channel.find(channel_name)
        assert_that(result, equal_to(None))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TENANT_UUID, do_not_disturb=False)
    def test_initiate_user_services(self, _, user):
        confd_users = [
            {
                'uuid': USER_UUID,
                'tenant_uuid': TENANT_UUID,
                'services': {'dnd': {'enabled': True}},
            },
        ]

        self.initiator._update_services_users(confd_users)

        result = self._dao.user.get([TENANT_UUID], USER_UUID)
        assert_that(result, has_properties(do_not_disturb=True))
