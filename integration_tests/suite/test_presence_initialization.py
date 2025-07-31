# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import random
import uuid

from hamcrest import (
    assert_that,
    calling,
    contains_inanyorder,
    has_entries,
    has_items,
    has_properties,
    not_,
)
from wazo_chatd_client.exceptions import ChatdError
from wazo_test_helpers import until
from wazo_test_helpers.hamcrest.raises import raises

from wazo_chatd.database import models

from .helpers import fixtures
from .helpers.base import (
    CHATD_TOKEN_TENANT_UUID,
    TOKEN_TENANT_UUID,
    InitIntegrationTest,
    use_asset,
)
from .helpers.wait_strategy import (
    BusOkWaitStrategy,
    PresenceInitOkWaitStrategy,
    RestApiOkWaitStrategy,
)

TENANT_UUID = uuid.uuid4()
USER_UUID_1 = uuid.uuid4()
USER_UUID_2 = uuid.uuid4()
LINE_ID_1 = 6
LINE_ID_2 = 42
ENDPOINT_NAME = 'CUSTOM/name'
FAKE_UUID_STR = str(uuid.uuid4())


@use_asset('initialization')
class TestPresenceInitialization(InitIntegrationTest):
    @fixtures.db.endpoint()
    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='available')
    @fixtures.db.tenant()
    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_UUID)
    @fixtures.db.user(
        uuid=USER_UUID_2,
        tenant_uuid=TENANT_UUID,
        state='available',
        do_not_disturb=False,
    )
    @fixtures.db.session(user_uuid=USER_UUID_1)
    @fixtures.db.session(user_uuid=USER_UUID_2)
    @fixtures.db.refresh_token(client_id='deleted', user_uuid=USER_UUID_1)
    @fixtures.db.refresh_token(client_id='unchanged', user_uuid=USER_UUID_2)
    @fixtures.db.line(id=LINE_ID_1, user_uuid=USER_UUID_1)
    @fixtures.db.line(id=LINE_ID_2, user_uuid=USER_UUID_2, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(line_id=LINE_ID_1)
    @fixtures.db.channel(
        line_id=LINE_ID_2, state='talking', name=f'{ENDPOINT_NAME}-0001'
    )
    def test_initialization(
        self,
        endpoint_deleted,
        endpoint_unchanged,
        tenant_deleted,
        tenant_unchanged,
        user_deleted,
        user_unchanged,
        session_deleted,
        session_unchanged,
        refresh_token_deleted,
        refresh_token_unchanged,
        line_deleted,
        line_unchanged,
        channel_deleted,
        channel_unchanged,
    ):
        # setup tenants
        tenant_created_uuid = uuid.uuid4()
        self.auth.set_tenants(
            {
                'uuid': str(CHATD_TOKEN_TENANT_UUID),
                'parent_uuid': str(CHATD_TOKEN_TENANT_UUID),
            },
            {
                'uuid': str(tenant_created_uuid),
                'parent_uuid': str(CHATD_TOKEN_TENANT_UUID),
            },
            {
                'uuid': str(tenant_unchanged.uuid),
                'parent_uuid': str(CHATD_TOKEN_TENANT_UUID),
            },
        )

        # setup users/lines
        user_created_uuid = uuid.uuid4()
        line_1_created_name = 'created_1'
        line_2_created_name = 'created_2'
        line_1_created_id = random.randint(1, 1000000)
        line_2_created_id = random.randint(1, 1000000)
        line_bugged_id = random.randint(1, 1000000)
        self.confd.set_users(
            {
                'uuid': str(user_created_uuid),
                'tenant_uuid': str(tenant_created_uuid),
                'lines': [
                    {
                        'id': line_1_created_id,
                        'name': line_1_created_name,
                        'endpoint_sip': {'uuid': FAKE_UUID_STR},
                    },
                    {
                        'id': line_2_created_id,
                        'name': line_2_created_name,
                        'endpoint_sccp': {'id': 1},
                    },
                    {
                        'id': line_bugged_id,
                        'name': None,
                        'endpoint_sip': {'uuid': FAKE_UUID_STR},
                    },
                ],
                'services': {'dnd': {'enabled': True}},
            },
            {
                'uuid': str(user_unchanged.uuid),
                'tenant_uuid': str(user_unchanged.tenant_uuid),
                'lines': [
                    {
                        'id': line_unchanged.id,
                        'name': ENDPOINT_NAME,
                        'endpoint_custom': {'id': 1},
                    }
                ],
                'services': {'dnd': {'enabled': False}},
            },
        )

        # setup endpoints
        endpoint_1_created_name = f'PJSIP/{line_1_created_name}'
        endpoint_2_created_name = f'SCCP/{line_2_created_name}'
        self.amid.set_devicestatelist(
            {
                "Event": "DeviceStateChange",
                "Device": endpoint_1_created_name,
                "State": "ONHOLD",
            },
            # Simulate no SCCP device returned by asterisk
            # {
            #     "Event": "DeviceStateChange",
            #     "Device": endpoint_2_created_name,
            #     "State": "NOT_INUSE"
            # },
            {
                "Event": "DeviceStateChange",
                "Device": endpoint_unchanged.name,
                "State": "INUSE",
            },
        )

        # setup channels
        channel_created_name = f'{endpoint_1_created_name}-1234'
        channel_unchanged_name = channel_unchanged.name
        self.amid.set_coreshowchannels(
            {
                "Event": "CoreShowChannel",
                "Channel": channel_created_name,
                "ChannelStateDesc": "Ringing",
                "ChanVariable": {"XIVO_ON_HOLD": "1"},
            },
            {
                "Event": "CoreShowChannel",
                "Channel": channel_unchanged.name,
                "ChannelStateDesc": "Up",
                "ChanVariable": {"XIVO_ON_HOLD": ""},
            },
        )

        # setup sessions
        session_created_uuid = uuid.uuid4()
        self.auth.set_sessions(
            {
                'uuid': str(session_created_uuid),
                'user_uuid': str(user_created_uuid),
                'tenant_uuid': str(tenant_created_uuid),
                'mobile': True,
            },
            {
                'uuid': str(session_unchanged.uuid),
                'user_uuid': str(session_unchanged.user_uuid),
                'tenant_uuid': str(session_unchanged.tenant_uuid),
                'mobile': session_unchanged.mobile,
            },
        )

        # setup refresh_tokens
        refresh_token_created_client_id = 'created'
        self.auth.set_refresh_tokens(
            {
                'client_id': refresh_token_created_client_id,
                'user_uuid': str(user_created_uuid),
                'tenant_uuid': str(tenant_created_uuid),
                'mobile': True,
            },
            {
                'client_id': 'unchanged',
                'user_uuid': str(refresh_token_unchanged.user_uuid),
                'tenant_uuid': str(refresh_token_unchanged.tenant_uuid),
                'mobile': refresh_token_unchanged.mobile,
            },
        )

        # start initialization
        self.restart_chatd_service()
        PresenceInitOkWaitStrategy().wait(self)

        self._session.expire_all()

        # test tenants
        tenants = self._dao.tenant.list_()
        assert_that(
            tenants,
            contains_inanyorder(
                has_properties(uuid=CHATD_TOKEN_TENANT_UUID),
                has_properties(uuid=tenant_unchanged.uuid),
                has_properties(uuid=tenant_created_uuid),
            ),
        )

        # test users
        users = self._dao.user.list_(tenant_uuids=None)
        assert_that(
            users,
            contains_inanyorder(
                has_properties(
                    uuid=user_unchanged.uuid,
                    tenant_uuid=tenant_unchanged.uuid,
                    state='available',
                    do_not_disturb=False,
                ),
                has_properties(
                    uuid=user_created_uuid,
                    tenant_uuid=tenant_created_uuid,
                    state='unavailable',
                    do_not_disturb=True,
                ),
            ),
        )

        # test sessions
        sessions = self._session.query(models.Session).all()
        assert_that(
            sessions,
            contains_inanyorder(
                has_properties(
                    uuid=session_unchanged.uuid,
                    user_uuid=user_unchanged.uuid,
                    mobile=session_unchanged.mobile,
                ),
                has_properties(
                    uuid=session_created_uuid,
                    user_uuid=user_created_uuid,
                    mobile=True,
                ),
            ),
        )

        # test refresh_tokens
        refresh_tokens = self._session.query(models.RefreshToken).all()
        assert_that(
            refresh_tokens,
            contains_inanyorder(
                has_properties(
                    client_id=refresh_token_unchanged.client_id,
                    user_uuid=user_unchanged.uuid,
                    mobile=refresh_token_unchanged.mobile,
                ),
                has_properties(
                    client_id=refresh_token_created_client_id,
                    user_uuid=user_created_uuid,
                    mobile=True,
                ),
            ),
        )

        # test lines
        lines = self._session.query(models.Line).all()
        assert_that(
            lines,
            contains_inanyorder(
                has_properties(
                    id=line_unchanged.id,
                    user_uuid=user_unchanged.uuid,
                    endpoint_name=endpoint_unchanged.name,
                ),
                has_properties(
                    id=line_1_created_id,
                    user_uuid=user_created_uuid,
                    endpoint_name=endpoint_1_created_name,
                ),
                has_properties(
                    id=line_2_created_id,
                    user_uuid=user_created_uuid,
                    endpoint_name=endpoint_2_created_name,
                ),
                has_properties(
                    id=line_bugged_id, user_uuid=user_created_uuid, endpoint_name=None
                ),
            ),
        )

        # test endpoints
        lines = self._session.query(models.Endpoint).all()
        assert_that(
            lines,
            contains_inanyorder(
                has_properties(name=endpoint_unchanged.name, state='available'),
                has_properties(name=endpoint_1_created_name, state='available'),
                has_properties(name=endpoint_2_created_name, state='unavailable'),
            ),
        )

        # test channels
        lines = self._session.query(models.Channel).all()
        assert_that(
            lines,
            contains_inanyorder(
                has_properties(name=channel_unchanged_name, state='talking'),
                has_properties(name=channel_created_name, state='holding'),
            ),
        )


@use_asset('initialization')
class TestAsteriskFullyBooted(InitIntegrationTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        PresenceInitOkWaitStrategy().wait(cls)
        cls.auth.clear_requests()

    def test_fullybooted_event_received(self):
        user_created_uuid = uuid.uuid4()
        self.confd.set_users(
            {
                'uuid': str(user_created_uuid),
                'tenant_uuid': str(TOKEN_TENANT_UUID),
                'lines': [],
                'services': {'dnd': {'enabled': True}},
            },
        )

        self.bus.send_fullybooted_event()

        def db_updated():
            users = self._dao.user.list_(tenant_uuids=None)
            assert_that(
                users, contains_inanyorder(has_properties(uuid=user_created_uuid))
            )

        until.assert_(db_updated, tries=10)

    def test_multiple_fullybooted_events_do_not_impact(self):
        user_created_uuid = uuid.uuid4()
        self.confd.set_users(
            {
                'uuid': str(user_created_uuid),
                'tenant_uuid': str(TOKEN_TENANT_UUID),
                'lines': [],
                'services': {'dnd': {'enabled': True}},
            },
        )

        self.bus.send_fullybooted_event()
        self.bus.send_fullybooted_event()  # ignored
        self.bus.send_fullybooted_event()  # ignored

        def db_updated():
            users = self._dao.user.list_(tenant_uuids=None)
            assert_that(
                users, contains_inanyorder(has_properties(uuid=user_created_uuid))
            )

        until.assert_(db_updated, tries=10)

    def test_fullybooted_can_handle_events(self):
        user_created_uuid = uuid.uuid4()
        self.confd.set_users(
            {
                'uuid': str(user_created_uuid),
                'tenant_uuid': str(TOKEN_TENANT_UUID),
                'lines': [],
                'services': {'dnd': {'enabled': True}},
            },
            delay=3,
        )

        self.bus.send_fullybooted_event()

        created_tenant_uuid = uuid.uuid4()
        dropped_user_uuid = uuid.uuid4()
        with self.ensure_being_in_fetching_users_stage():
            self.bus.send_tenant_created_event(created_tenant_uuid)
            self.bus.send_user_created_event(dropped_user_uuid, TOKEN_TENANT_UUID)

        PresenceInitOkWaitStrategy().wait(self)

        self._session.expire_all()
        tenants = self._dao.tenant.list_()
        assert_that(tenants, has_items(has_properties(uuid=created_tenant_uuid)))
        users = self._dao.user.list_(tenant_uuids=None)
        assert_that(users, not_(has_items(has_properties(uuid=dropped_user_uuid))))


@use_asset('initialization')
class TestHandleEvents(InitIntegrationTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Avoid race condition when clearing requests
        PresenceInitOkWaitStrategy().wait(cls)
        cls.auth.clear_requests()

    def test_initialization_can_handle_events(self):
        user_created_uuid = uuid.uuid4()
        self.confd.set_users(
            {
                'uuid': str(user_created_uuid),
                'tenant_uuid': str(TOKEN_TENANT_UUID),
                'lines': [],
                'services': {'dnd': {'enabled': True}},
            },
            delay=3,
        )

        self.restart_chatd_service()
        BusOkWaitStrategy().wait(self)

        created_tenant_uuid = uuid.uuid4()
        dropped_user_uuid = uuid.uuid4()
        with self.ensure_being_in_fetching_users_stage():
            self.bus.send_tenant_created_event(created_tenant_uuid)
            self.bus.send_user_created_event(dropped_user_uuid, TOKEN_TENANT_UUID)

        PresenceInitOkWaitStrategy().wait(self)

        self._session.expire_all()
        tenants = self._dao.tenant.list_()
        assert_that(tenants, has_items(has_properties(uuid=created_tenant_uuid)))
        users = self._dao.user.list_(tenant_uuids=None)
        assert_that(users, not_(has_items(has_properties(uuid=dropped_user_uuid))))


@use_asset('initialization')
class TestPresenceInitializationErrors(InitIntegrationTest):
    def test_server_initialization_do_not_block_on_http_error(self):
        self.stop_chatd_service()
        self.stop_amid_service()
        self.start_chatd_service()
        RestApiOkWaitStrategy().wait(self)

        def server_wait():
            status = self.chatd.status.get()
            assert_that(
                status,
                has_entries(
                    {
                        'presence_initialization': has_entries(status='fail'),
                        'rest_api': has_entries(status='ok'),
                    }
                ),
            )

        until.assert_(server_wait, tries=5)

        self.start_amid_service()

        PresenceInitOkWaitStrategy().wait(self)

    def test_server_initialization_do_not_block_on_database_error(self):
        self.stop_chatd_service()
        self.stop_postgres_service()
        self.start_chatd_service()
        self.reset_clients()
        RestApiOkWaitStrategy().wait(self)

        def server_wait():
            status = self.chatd.status.get()
            assert_that(
                status,
                has_entries(
                    {
                        'presence_initialization': has_entries(status='fail'),
                        'rest_api': has_entries(status='ok'),
                    }
                ),
            )

        until.assert_(server_wait, tries=5)

        self.start_postgres_service()

        PresenceInitOkWaitStrategy().wait(self)

    @fixtures.db.user()
    def test_api_return_503(self, user):
        user_args = {'uuid': str(user.uuid), 'state': 'available'}
        self.stop_chatd_service()
        self.stop_amid_service()
        self.start_chatd_service()
        RestApiOkWaitStrategy().wait(self)

        assert_that(
            calling(self.chatd.user_presences.list),
            raises(
                ChatdError, has_properties(error_id='not-initialized', status_code=503)
            ),
        )

        assert_that(
            calling(self.chatd.user_presences.get).with_args(user_args['uuid']),
            raises(
                ChatdError, has_properties(error_id='not-initialized', status_code=503)
            ),
        )

        assert_that(
            calling(self.chatd.user_presences.update).with_args(user_args),
            raises(
                ChatdError, has_properties(error_id='not-initialized', status_code=503)
            ),
        )

        self.start_amid_service()
        PresenceInitOkWaitStrategy().wait(self)
        self.chatd.user_presences.list()
