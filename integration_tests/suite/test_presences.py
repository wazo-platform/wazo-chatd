# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    contains,
    contains_inanyorder,
    equal_to,
    empty,
    has_entries,
    has_properties,
    is_not,
    none,
)

from xivo_test_helpers.hamcrest.raises import raises

from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    BaseIntegrationTest,
    UNKNOWN_UUID,
    MASTER_TENANT_UUID,
    SUBTENANT_UUID,
)

USER_UUID = str(uuid.uuid4())
DEVICE_NAME_1 = 'PJSIP/name'
DEVICE_NAME_2 = 'SCCP/name'


class TestPresence(BaseIntegrationTest):

    asset = 'base'

    @fixtures.db.user()
    @fixtures.db.user()
    def test_list(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(presences, has_entries(
            items=contains(
                has_entries(
                    uuid=user_1.uuid,
                    tenant_uuid=user_1.tenant_uuid,
                    state=user_1.state,
                    status=user_1.status,
                    sessions=empty(),
                    lines=empty(),
                ),
                has_entries(
                    uuid=user_2.uuid,
                    tenant_uuid=user_2.tenant_uuid,
                    state=user_2.state,
                    status=user_2.status,
                    sessions=empty(),
                    lines=empty(),
                ),
            ),
            total=equal_to(2),
            filtered=equal_to(2),
        ))

    @fixtures.db.user(tenant_uuid=MASTER_TENANT_UUID)
    @fixtures.db.user(tenant_uuid=SUBTENANT_UUID)
    def test_list_multi_tenant(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(presences, has_entries(
            items=contains(has_entries(uuid=user_1.uuid)),
            total=equal_to(1),
            filtered=equal_to(1),
        ))

        presences = self.chatd.user_presences.list(recurse=True)
        assert_that(presences, has_entries(
            items=contains(has_entries(uuid=user_1.uuid), has_entries(uuid=user_2.uuid)),
            total=equal_to(2),
            filtered=equal_to(2),
        ))

    @fixtures.db.device(name=DEVICE_NAME_1, state='holding')
    @fixtures.db.device(name=DEVICE_NAME_2, state='talking')
    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.session(user_uuid=USER_UUID, mobile=True)
    @fixtures.db.session(user_uuid=USER_UUID, mobile=False)
    @fixtures.db.line(user_uuid=USER_UUID, device_name=DEVICE_NAME_1)
    @fixtures.db.line(user_uuid=USER_UUID, device_name=DEVICE_NAME_2)
    def test_get(self, device_1, device_2, user, session_1, session_2, line_1, line_2):
        presence = self.chatd.user_presences.get(user.uuid)
        assert_that(
            presence,
            has_entries(
                uuid=user.uuid,
                tenant_uuid=user.tenant_uuid,
                state=user.state,
                status=user.status,
                sessions=contains_inanyorder(
                    has_entries(uuid=session_1.uuid, mobile=True),
                    has_entries(uuid=session_2.uuid, mobile=False),
                ),
                lines=contains_inanyorder(
                    has_entries(id=line_1.id, state='holding'),
                    has_entries(id=line_2.id, state='talking'),
                ),
            ),
        )

    def test_get_unknown_uuid(self):
        assert_that(
            calling(self.chatd.user_presences.get).with_args(UNKNOWN_UUID),
            raises(
                ChatdError,
                has_properties(
                    status_code=404,
                    error_id='unknown-user',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                    timestamp=is_not(none()),
                )
            )
        )

    @fixtures.db.user(tenant_uuid=MASTER_TENANT_UUID)
    @fixtures.db.user(tenant_uuid=SUBTENANT_UUID)
    def test_get_multi_tenant(self, user_1, user_2):
        result = self.chatd.user_presences.get(user_2.uuid, tenant_uuid=SUBTENANT_UUID)
        assert_that(result, has_entries(uuid=user_2.uuid))

        assert_that(
            calling(self.chatd.user_presences.get).with_args(
                user_1.uuid, tenant_uuid=SUBTENANT_UUID,
            ),
            raises(ChatdError, has_properties(status_code=404))
        )

    @fixtures.db.user(state='unavailable')
    def test_update(self, user):
        user_args = {'uuid': user.uuid, 'state': 'invisible', 'status': 'custom status'}
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.chatd.user_presences.update(user_args)

        presence = self.chatd.user_presences.get(user_args['uuid'])
        assert_that(presence, has_entries(user_args))

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(user_args))))

    def test_update_unknown_uuid(self):
        assert_that(
            calling(self.chatd.user_presences.update).with_args({'uuid': UNKNOWN_UUID}),
            raises(
                ChatdError,
                has_properties(
                    status_code=404,
                    error_id='unknown-user',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                    timestamp=is_not(none()),
                )
            )
        )

    @fixtures.db.user(tenant_uuid=MASTER_TENANT_UUID)
    @fixtures.db.user(tenant_uuid=SUBTENANT_UUID, state='unavailable')
    def test_update_multi_tenant(self, user_1, user_2):
        user_args = {'uuid': user_2.uuid, 'state': 'available'}
        self.chatd.user_presences.update(user_args, tenant_uuid=SUBTENANT_UUID)

        result = self.chatd.user_presences.get(user_args['uuid'])
        assert_that(result, has_entries(user_args))

        assert_that(
            calling(self.chatd.user_presences.update).with_args(
                {'uuid': user_1.uuid}, tenant_uuid=SUBTENANT_UUID,
            ),
            raises(ChatdError, has_properties(status_code=404))
        )
