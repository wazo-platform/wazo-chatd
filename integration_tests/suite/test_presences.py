# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
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
    not_,
)

from xivo_test_helpers.hamcrest.raises import raises

from wazo_chatd_client.exceptions import ChatdError

from .helpers import fixtures
from .helpers.base import (
    APIIntegrationTest,
    TOKEN_SUBTENANT_UUID,
    TOKEN_TENANT_UUID,
    UNKNOWN_UUID,
    use_asset,
)

USER_UUID = uuid.uuid4()
LINE_ID_1 = 42
ENDPOINT_NAME_1 = 'PJSIP/name'
ENDPOINT_NAME_2 = 'SCCP/name'


@use_asset('base')
class TestPresence(APIIntegrationTest):
    @fixtures.db.user()
    @fixtures.db.user()
    def test_list(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(
            presences,
            has_entries(
                items=contains(
                    has_entries(
                        uuid=str(user_1.uuid),
                        tenant_uuid=str(user_1.tenant_uuid),
                        state=user_1.state,
                        status=user_1.status,
                        last_activity=none(),
                        line_state='unavailable',
                        do_not_disturb=False,
                        mobile=False,
                        sessions=empty(),
                        lines=empty(),
                    ),
                    has_entries(
                        uuid=str(user_2.uuid),
                        tenant_uuid=str(user_2.tenant_uuid),
                        state=user_2.state,
                        status=user_2.status,
                        last_activity=none(),
                        line_state='unavailable',
                        do_not_disturb=False,
                        mobile=False,
                        sessions=empty(),
                        lines=empty(),
                    ),
                ),
                total=equal_to(2),
                filtered=equal_to(2),
            ),
        )

    @fixtures.db.user(tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user(tenant_uuid=TOKEN_SUBTENANT_UUID)
    def test_list_multi_tenant(self, user_1, user_2):
        presences = self.chatd.user_presences.list()
        assert_that(
            presences,
            has_entries(
                items=contains(has_entries(uuid=str(user_1.uuid))),
                total=equal_to(1),
                filtered=equal_to(1),
            ),
        )

        presences = self.chatd.user_presences.list(recurse=True)
        assert_that(
            presences,
            has_entries(
                items=contains(
                    has_entries(uuid=str(user_1.uuid)),
                    has_entries(uuid=str(user_2.uuid)),
                ),
                total=equal_to(2),
                filtered=equal_to(2),
            ),
        )

    @fixtures.db.user()
    @fixtures.db.user()
    @fixtures.db.user()
    def test_list_user_uuids(self, user_1, user_2, user_3):
        presences = self.chatd.user_presences.list(
            user_uuids=[str(user_1.uuid), str(user_2.uuid)]
        )
        assert_that(
            presences,
            has_entries(
                items=contains(
                    has_entries(uuid=str(user_1.uuid)),
                    has_entries(uuid=str(user_2.uuid)),
                ),
                total=equal_to(3),
                filtered=equal_to(2),
            ),
        )

    def test_list_unknown_user_uuids(self):
        # NOTE(fblackburn): list should not return error on unknown users
        assert_that(
            calling(self.chatd.user_presences.list).with_args(
                user_uuids=[str(UNKNOWN_UUID)]
            ),
            raises(
                ChatdError,
                has_properties(
                    status_code=404,
                    error_id='unknown-users',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                    timestamp=is_not(none()),
                ),
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME_1, state='unavailable')
    @fixtures.db.endpoint(name=ENDPOINT_NAME_2, state='available')
    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.session(user_uuid=USER_UUID, mobile=True)
    @fixtures.db.session(user_uuid=USER_UUID, mobile=False)
    @fixtures.db.refresh_token(user_uuid=USER_UUID, mobile=True)
    @fixtures.db.refresh_token(user_uuid=USER_UUID, mobile=False)
    @fixtures.db.line(id=LINE_ID_1, user_uuid=USER_UUID, endpoint_name=ENDPOINT_NAME_1)
    @fixtures.db.line(user_uuid=USER_UUID, endpoint_name=ENDPOINT_NAME_2)
    @fixtures.db.channel(line_id=LINE_ID_1, state='undefined')
    @fixtures.db.channel(line_id=LINE_ID_1, state='holding')
    def test_get(
        self,
        endpoint_1,
        endpoint_2,
        user,
        session_1,
        session_2,
        _,
        __,
        line_1,
        line_2,
        ___,
        ____,
    ):
        presence = self.chatd.user_presences.get(str(user.uuid))
        assert_that(
            presence,
            has_entries(
                uuid=str(user.uuid),
                tenant_uuid=str(user.tenant_uuid),
                state=user.state,
                status=user.status,
                last_activity=none(),
                line_state='holding',
                do_not_disturb=False,
                mobile=True,
                sessions=contains_inanyorder(
                    has_entries(uuid=str(session_1.uuid), mobile=True),
                    has_entries(uuid=str(session_2.uuid), mobile=False),
                ),
                lines=contains_inanyorder(
                    has_entries(id=line_1.id, state='holding'),
                    has_entries(id=line_2.id, state='available'),
                ),
            ),
        )

    def test_get_unknown_uuid(self):
        assert_that(
            calling(self.chatd.user_presences.get).with_args(str(UNKNOWN_UUID)),
            raises(
                ChatdError,
                has_properties(
                    status_code=404,
                    error_id='unknown-user',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                    timestamp=is_not(none()),
                ),
            ),
        )

    @fixtures.db.user(tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user(tenant_uuid=TOKEN_SUBTENANT_UUID)
    def test_get_multi_tenant(self, user_1, user_2):
        result = self.chatd.user_presences.get(
            str(user_2.uuid), tenant_uuid=str(TOKEN_SUBTENANT_UUID)
        )
        assert_that(result, has_entries(uuid=str(user_2.uuid)))

        assert_that(
            calling(self.chatd.user_presences.get).with_args(
                str(user_1.uuid), tenant_uuid=str(TOKEN_SUBTENANT_UUID)
            ),
            raises(ChatdError, has_properties(status_code=404)),
        )

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.session(user_uuid=USER_UUID, mobile=False)
    @fixtures.db.session(user_uuid=USER_UUID, mobile=True)
    def test_get_mobile_when_session(self, user, session_1, session_2):
        presence = self.chatd.user_presences.get(user.uuid)
        assert_that(
            presence,
            has_entries(
                uuid=str(user.uuid),
                tenant_uuid=str(user.tenant_uuid),
                mobile=True,
                sessions=contains_inanyorder(
                    has_entries(uuid=str(session_1.uuid), mobile=False),
                    has_entries(uuid=str(session_2.uuid), mobile=True),
                ),
            ),
        )

    @fixtures.db.user(uuid=USER_UUID)
    @fixtures.db.refresh_token(user_uuid=USER_UUID, mobile=False)
    @fixtures.db.refresh_token(user_uuid=USER_UUID, mobile=True)
    def test_get_mobile_when_refresh_token(self, user, token_1, token_2):
        presence = self.chatd.user_presences.get(user.uuid)
        assert_that(
            presence,
            has_entries(
                uuid=str(user.uuid),
                tenant_uuid=str(user.tenant_uuid),
                mobile=True,
            ),
        )

    @fixtures.db.user(uuid=USER_UUID)
    def test_get_mobile_when_no_session_or_refresh_token(self, user):
        presence = self.chatd.user_presences.get(str(user.uuid))
        assert_that(
            presence,
            has_entries(
                uuid=str(user.uuid),
                tenant_uuid=str(user.tenant_uuid),
                mobile=False,
            ),
        )

    @fixtures.db.user(state='away')
    def test_update(self, user):
        user_args = {
            'uuid': str(user.uuid),
            'state': 'invisible',
            'status': 'custom status',
        }
        routing_key = 'chatd.users.*.presences.updated'
        event_accumulator = self.bus.accumulator(routing_key)

        self.chatd.user_presences.update(user_args)

        presence = self.chatd.user_presences.get(user_args['uuid'])
        assert_that(presence, has_entries(last_activity=not_(none()), **user_args))

        event = event_accumulator.accumulate()
        assert_that(
            event,
            contains(
                has_entries(data=has_entries(last_activity=not_(none()), **user_args))
            ),
        )

    def test_update_unknown_uuid(self):
        assert_that(
            calling(self.chatd.user_presences.update).with_args(
                {'uuid': str(UNKNOWN_UUID)}
            ),
            raises(
                ChatdError,
                has_properties(
                    status_code=404,
                    error_id='unknown-user',
                    resource='users',
                    details=is_not(none()),
                    message=is_not(none()),
                    timestamp=is_not(none()),
                ),
            ),
        )

    @fixtures.db.user(tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user(tenant_uuid=TOKEN_SUBTENANT_UUID, state='unavailable')
    def test_update_multi_tenant(self, user_1, user_2):
        user_args = {'uuid': str(user_2.uuid), 'state': 'available'}
        self.chatd.user_presences.update(
            user_args, tenant_uuid=str(TOKEN_SUBTENANT_UUID)
        )

        result = self.chatd.user_presences.get(user_args['uuid'])
        assert_that(result, has_entries(user_args))

        assert_that(
            calling(self.chatd.user_presences.update).with_args(
                {'uuid': str(user_1.uuid)}, tenant_uuid=str(TOKEN_SUBTENANT_UUID)
            ),
            raises(ChatdError, has_properties(status_code=404)),
        )
