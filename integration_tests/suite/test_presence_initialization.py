# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import random
import uuid

from hamcrest import (
    assert_that,
    contains_inanyorder,
    has_properties,
)

from wazo_chatd.database import models

from .helpers import fixtures
from .helpers.wait_strategy import EverythingOkWaitStrategy
from .helpers.base import (
    BaseIntegrationTest,
    VALID_TOKEN,
)

TENANT_UUID = str(uuid.uuid4())
USER_UUID_1 = str(uuid.uuid4())
USER_UUID_2 = str(uuid.uuid4())
ENDPOINT_NAME = 'CUSTOM/name'


class TestPresenceInitialization(BaseIntegrationTest):

    asset = 'initialization'
    wait_strategy = EverythingOkWaitStrategy()

    @fixtures.db.endpoint()
    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='available')
    @fixtures.db.tenant()
    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID_2, tenant_uuid=TENANT_UUID, state='available')
    @fixtures.db.session(user_uuid=USER_UUID_1)
    @fixtures.db.session(user_uuid=USER_UUID_2)
    @fixtures.db.line(user_uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_2, endpoint_name=ENDPOINT_NAME)
    def test_initialization(
        self,
        endpoint_deleted, endpoint_unchanged,
        tenant_deleted, tenant_unchanged,
        user_deleted, user_unchanged,
        session_deleted, session_unchanged,
        line_deleted, line_unchanged,
    ):
        # setup tenants
        tenant_created_uuid = str(uuid.uuid4())
        self.auth.set_tenants({
            'items': [
                {'uuid': tenant_created_uuid},
                {'uuid': tenant_unchanged.uuid},
            ]
        })

        # setup users/lines
        user_created_uuid = str(uuid.uuid4())
        line_1_created_name = 'created_1'
        line_2_created_name = 'created_2'
        line_1_created_id = random.randint(1, 1000000)
        line_2_created_id = random.randint(1, 1000000)
        self.confd.set_users(
            {
                'uuid': user_created_uuid,
                'tenant_uuid': tenant_created_uuid,
                'lines': [
                    {
                        'id': line_1_created_id,
                        'name': line_1_created_name,
                        'endpoint_sip': {'id': 1}
                    },
                    {
                        'id': line_2_created_id,
                        'name': line_2_created_name,
                        'endpoint_sccp': {'id': 1}
                    },
                ]
            },
            {
                'uuid': user_unchanged.uuid,
                'tenant_uuid': user_unchanged.tenant_uuid,
                'lines': [
                    {
                        'id': line_unchanged.id,
                        'name': ENDPOINT_NAME,
                        'endpoint_custom': {'id': 1},
                    }
                ],
            },
        )

        # setup endpoints
        endpoint_1_created_name = 'PJSIP/{}'.format(line_1_created_name)
        endpoint_2_created_name = 'SCCP/{}'.format(line_2_created_name)
        self.amid.set_devicestatelist(
            {
                "Event": "DeviceStateChange",
                "Device": endpoint_1_created_name,
                "State": "ONHOLD"
            },
            {
                "Event": "DeviceStateChange",
                "Device": endpoint_2_created_name,
                "State": "NOT_INUSE"
            },
            {
                "Event": "DeviceStateChange",
                "Device": endpoint_unchanged.name,
                "State": "INUSE"
            },
        )

        # setup sessions
        session_created_uuid = str(uuid.uuid4())
        self.auth.set_sessions({
            'items': [
                {
                    'uuid': session_created_uuid,
                    'user_uuid': user_created_uuid,
                    'tenant_uuid': tenant_created_uuid,
                },
                {
                    'uuid': session_unchanged.uuid,
                    'user_uuid': session_unchanged.user_uuid,
                    'tenant_uuid': user_unchanged.tenant_uuid,
                },
            ]
        })

        # start initialization
        self.restart_service('chatd')
        self.chatd = self.make_chatd(VALID_TOKEN)
        EverythingOkWaitStrategy().wait(self)

        self._session.expire_all()

        # test tenants
        tenants = self._dao.tenant.list_()
        assert_that(tenants, contains_inanyorder(
            has_properties(uuid=tenant_unchanged.uuid),
            has_properties(uuid=tenant_created_uuid),
        ))

        # test users
        users = self._dao.user.list_(tenant_uuids=None)
        assert_that(users, contains_inanyorder(
            has_properties(
                uuid=user_unchanged.uuid,
                tenant_uuid=tenant_unchanged.uuid,
                state='available',
            ),
            has_properties(
                uuid=user_created_uuid,
                tenant_uuid=tenant_created_uuid,
                state='unavailable',
            ),
        ))

        # test sessions
        sessions = self._session.query(models.Session).all()
        assert_that(sessions, contains_inanyorder(
            has_properties(uuid=session_unchanged.uuid, user_uuid=user_unchanged.uuid),
            has_properties(uuid=session_created_uuid, user_uuid=user_created_uuid),
        ))

        # test lines
        lines = self._session.query(models.Line).all()
        assert_that(lines, contains_inanyorder(
            has_properties(
                id=line_unchanged.id,
                user_uuid=user_unchanged.uuid,
                endpoint_name=endpoint_unchanged.name
            ),
            has_properties(
                id=line_1_created_id,
                user_uuid=user_created_uuid,
                endpoint_name=endpoint_1_created_name
            ),
            has_properties(
                id=line_2_created_id,
                user_uuid=user_created_uuid,
                endpoint_name=endpoint_2_created_name
            ),
        ))

        # test endpoints
        lines = self._session.query(models.Endpoint).all()
        assert_that(lines, contains_inanyorder(
            has_properties(name=endpoint_unchanged.name, state='talking'),
            has_properties(name=endpoint_1_created_name, state='holding'),
            has_properties(name=endpoint_2_created_name, state='available'),
        ))
