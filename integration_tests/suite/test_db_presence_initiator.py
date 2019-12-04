# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from mock import Mock
from hamcrest import assert_that, equal_to

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy
from wazo_chatd.plugins.presences.initiator import Initiator

TENANT_UUID = str(uuid.uuid4())
USER_UUID = str(uuid.uuid4())
UNKNOWN_UUID = str(uuid.uuid4())
RANDOM_UUID = str(uuid.uuid4())


class TestDBPresenceInitiator(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    def setUp(self):
        super().setUp()
        self.initiator = Initiator(self._dao, Mock, Mock, Mock)

    @fixtures.db.tenant(uuid=TENANT_UUID)
    def test_initiate_session_when_no_user_associate(self, tenant):
        session_uuid = str(uuid.uuid4())
        sessions = [
            {'uuid': session_uuid, 'user_uuid': USER_UUID, 'tenant_uuid': TENANT_UUID}
        ]

        self.initiator.initiate_sessions(sessions)

        result = self._dao.session.find(session_uuid)
        assert_that(result, equal_to(None))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    def test_initiate_refresh_token_when_no_user_associate(self, tenant):
        client_id = 'my-client-id'
        refresh_tokens = [
            {'client_id': client_id, 'user_uuid': USER_UUID, 'tenant_uuid': TENANT_UUID}
        ]

        self.initiator.initiate_refresh_tokens(refresh_tokens)

        result = self._dao.refresh_token.find(USER_UUID, client_id)
        assert_that(result, equal_to(None))
