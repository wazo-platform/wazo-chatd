# Copyright 2019-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import random
import uuid

from hamcrest import (
    assert_that,
    contains,
    empty,
    has_entries,
    has_items,
    has_properties,
    not_,
)
from wazo_test_helpers import until

from wazo_chatd.database import models

from .helpers import fixtures
from .helpers.base import TOKEN_TENANT_UUID, APIIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()
LINE_ID = 42
ENDPOINT_NAME = 'PJSIP/name'


@use_asset('base')
class TestEventHandler(APIIntegrationTest):
    def test_tenant_created(self):
        tenant_uuid = uuid.uuid4()
        self.bus.send_tenant_created_event(tenant_uuid)

        def tenant_created():
            result = self._dao.tenant.list_()
            assert_that(result, has_items(has_properties(uuid=tenant_uuid)))

        until.assert_(tenant_created, tries=3)

    @fixtures.db.tenant()
    def test_tenant_deleted(self, tenant):
        tenant_uuid = tenant.uuid
        self.bus.send_tenant_deleted_event(tenant_uuid)

        def tenant_deleted():
            result = self._dao.tenant.list_()
            assert_that(result, not_(has_items(has_properties(uuid=tenant_uuid))))

        until.assert_(tenant_deleted, tries=3)

    def test_user_created(self):
        user_uuid = uuid.uuid4()
        tenant_uuid = uuid.uuid4()
        self.bus.send_user_created_event(user_uuid, tenant_uuid)

        def user_created():
            result = self._dao.user.list_(tenant_uuids=None)
            assert_that(
                result,
                has_items(has_properties(uuid=user_uuid, tenant_uuid=tenant_uuid)),
            )

        until.assert_(user_created, tries=3)

    @fixtures.db.user()
    def test_user_deleted(self, user):
        user_uuid = user.uuid
        tenant_uuid = user.tenant_uuid
        self.bus.send_user_deleted_event(user_uuid, tenant_uuid)

        def user_deleted():
            result = self._dao.user.list_(tenant_uuids=None)
            assert_that(
                result,
                not_(
                    has_items(
                        has_properties(
                            uuid=str(user_uuid),
                            tenant_uuid=str(tenant_uuid),
                        )
                    )
                ),
            )

        until.assert_(user_deleted, tries=3)

    @fixtures.db.user()
    def test_session_created(self, user):
        session_uuid = uuid.uuid4()
        user_uuid = user.uuid
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_session_created_event(
            session_uuid, user_uuid, user.tenant_uuid, mobile=True
        )

        def session_created():
            result = self._session.query(models.Session).all()
            assert_that(
                result,
                has_items(
                    has_properties(uuid=session_uuid, user_uuid=user_uuid, mobile=True)
                ),
            )

        until.assert_(session_created, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(data=has_entries(connected=True)),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.session(user_uuid=USER_UUID_1)
    def test_session_deleted(self, user, session):
        session_uuid = session.uuid
        user_uuid = user.uuid
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_session_deleted_event(session_uuid, user_uuid, user.tenant_uuid)

        def session_deleted():
            result = self._session.query(models.Session).all()
            assert_that(
                result,
                not_(has_items(has_properties(uuid=session_uuid, user_uuid=user_uuid))),
            )

        until.assert_(session_deleted, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(data=has_entries(connected=False)),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.user()
    def test_refresh_token_created(self, user):
        client_id = 'my-client-id'
        user_uuid = user.uuid
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_refresh_token_created_event(
            client_id, user_uuid, user.tenant_uuid, mobile=True
        )

        def refresh_token_created():
            result = self._session.query(models.RefreshToken).all()
            assert_that(
                result,
                has_items(has_properties(client_id=client_id, user_uuid=user_uuid)),
            )

        until.assert_(refresh_token_created, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(data=has_entries(mobile=True)),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.refresh_token(user_uuid=USER_UUID_1, mobile=True)
    def test_refresh_token_deleted(self, user, token):
        client_id = token.client_id
        user_uuid = user.uuid
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_refresh_token_deleted_event(
            client_id, user_uuid, user.tenant_uuid
        )

        def refresh_token_deleted():
            result = self._session.query(models.RefreshToken).all()
            assert_that(
                result,
                not_(
                    has_items(has_properties(client_id=client_id, user_uuid=user_uuid))
                ),
            )

        until.assert_(refresh_token_deleted, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(data=has_entries(mobile=False)),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.user()
    def test_user_line_associated(self, user):
        line_id = random.randint(1, 1000000)
        line_name = 'created-line'
        user_uuid = user.uuid
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_user_line_associated_event(
            line_id, user_uuid, user.tenant_uuid, line_name
        )

        def user_line_associated():
            result = self._session.query(models.Line).all()
            assert_that(
                result,
                has_items(
                    has_properties(
                        id=line_id,
                        user_uuid=user_uuid,
                        endpoint_name=f'PJSIP/{line_name}',
                    )
                ),
            )

        until.assert_(user_line_associated, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=line_id, state='unavailable'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.endpoint(name='PJSIP/myname', state='available')
    @fixtures.db.user()
    def test_user_line_associated_with_existing_endpoint(self, endpoint, user):
        line_id = random.randint(1, 1000000)
        line_name = 'myname'
        endpoint_state = endpoint.state
        user_uuid = user.uuid
        self.bus.send_user_line_associated_event(
            line_id, user_uuid, user.tenant_uuid, line_name
        )

        def user_line_associated():
            result = self._session.query(models.Line).all()
            assert_that(
                result,
                has_items(
                    has_properties(
                        endpoint_name=f'PJSIP/{line_name}',
                        endpoint_state=endpoint_state,
                    )
                ),
            )

        until.assert_(user_line_associated, tries=3)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user()
    @fixtures.db.line(user_uuid=USER_UUID_1)
    def test_user_line_associated_already_associated(self, user_1, user_2, line):
        line_id = line.id
        user_2_uuid = user_2.uuid

        self.bus.send_user_line_associated_event(
            line_id, user_2_uuid, user_2.tenant_uuid, None
        )

        def user_line_associated():
            self._session.expire_all()
            result = self._session.query(models.Line).all()
            assert_that(
                result, has_items(has_properties(id=line_id, user_uuid=user_2_uuid))
            )

        until.assert_(user_line_associated, tries=3)

    @fixtures.db.user()
    def test_user_line_associated_without_line_name(self, user):
        line_id = random.randint(1, 1000000)
        line_name = None
        user_uuid = user.uuid

        self.bus.send_user_line_associated_event(
            line_id, user_uuid, user.tenant_uuid, line_name
        )

        def user_line_associated():
            result = self._session.query(models.Line).all()
            assert_that(
                result, has_items(has_properties(id=line_id, endpoint_name=None))
            )

        until.assert_(user_line_associated, tries=3)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1)
    def test_user_line_dissociated(self, user, line):
        line_id = line.id
        user_uuid = user.uuid
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_line_dissociated_event(line_id, user_uuid, user.tenant_uuid)

        def user_line_dissociated():
            result = self._session.query(models.Line).all()
            assert_that(
                result, not_(has_items(has_properties(id=line_id, user_uuid=user_uuid)))
            )

        until.assert_(user_line_dissociated, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(data=has_entries(lines=empty())),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='unavailable')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    def test_device_state_changed(self, endpoint, user, line):
        line_id = line.id
        endpoint_name = endpoint.name
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_device_state_changed_event(endpoint_name, 'ONHOLD')

        def endpoint_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result, has_items(has_properties(name=endpoint_name, state='available'))
            )

        until.assert_(endpoint_state_changed, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=line_id, state='available'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    def test_device_state_changed_create_endpoint(self):
        endpoint_name = 'PJSIP/missing-endpoint'

        self.bus.send_device_state_changed_event(endpoint_name, 'ONHOLD')

        def endpoint_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result, has_items(has_properties(name=endpoint_name, state='available'))
            )

        until.assert_(endpoint_state_changed, tries=3)

    @fixtures.db.endpoint(name=ENDPOINT_NAME)
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    def test_new_channel(self, _, user, line):
        line_id = line.id
        channel_name = f'{line.endpoint_name}-1234'
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_new_channel_event(channel_name)

        def channel_created():
            self._session.expire_all()
            result = self._session.query(models.Channel).all()
            assert_that(
                result,
                has_items(has_properties(name=channel_name, state='progressing')),
            )

        until.assert_(channel_created, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=line_id, state='progressing'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='available')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(id=LINE_ID, user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(line_id=LINE_ID, name=f'{ENDPOINT_NAME}-1234')
    def test_hangup(self, _, user, line, channel):
        channel_name = channel.name
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_hangup_event(channel_name)

        def channel_deleted():
            self._session.expire_all()
            result = self._session.query(models.Channel).all()
            assert_that(result, not_(has_items(has_properties(name=channel_name))))

        until.assert_(channel_deleted, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=LINE_ID, state='available'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME)
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(id=LINE_ID, user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(line_id=LINE_ID, name=f'{ENDPOINT_NAME}-1234', state='holding')
    def test_new_state(self, _, user, line, channel):
        channel_name = channel.name
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_new_state_event(channel_name, state='Up')

        def channel_updated():
            self._session.expire_all()
            result = self._session.query(models.Channel).all()
            assert_that(
                result, has_items(has_properties(name=channel_name, state='talking'))
            )

        until.assert_(channel_updated, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=LINE_ID, state='talking'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME)
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(id=LINE_ID, user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(line_id=LINE_ID, name=f'{ENDPOINT_NAME}-1234', state='talking')
    def test_hold(self, _, user, line, channel):
        channel_name = channel.name
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_hold_event(channel_name)

        def channel_held():
            self._session.expire_all()
            result = self._session.query(models.Channel).all()
            assert_that(
                result, has_items(has_properties(name=channel_name, state='holding'))
            )

        until.assert_(channel_held, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=LINE_ID, state='holding'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME)
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(id=LINE_ID, user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    @fixtures.db.channel(line_id=LINE_ID, name=f'{ENDPOINT_NAME}-1234', state='holding')
    def test_unhold(self, _, user, line, channel):
        channel_name = channel.name
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )

        self.bus.send_unhold_event(channel_name)

        def channel_unheld():
            self._session.expire_all()
            result = self._session.query(models.Channel).all()
            assert_that(
                result, has_items(has_properties(name=channel_name, state='talking'))
            )

        until.assert_(channel_unheld, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=LINE_ID, state='talking'))
                        )
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )

    @fixtures.db.user(do_not_disturb=False)
    def test_do_not_disturb(self, user):
        event_accumulator = self.bus.accumulator(
            headers={'name': 'chatd_presence_updated', 'user_uuid:*': True}
        )
        user_uuid = str(user.uuid)

        self.bus.send_dnd_event(user_uuid, user.tenant_uuid, True)

        def dnd_updated():
            self._session.expire_all()
            result = self._session.query(models.User).all()
            assert_that(
                result, has_items(has_properties(uuid=user.uuid, do_not_disturb=True))
            )

        until.assert_(dnd_updated, tries=3)

        event = event_accumulator.accumulate(with_headers=True)
        assert_that(
            event,
            contains(
                has_entries(
                    message=has_entries(
                        data=has_entries(uuid=user_uuid, do_not_disturb=True)
                    ),
                    headers=has_entries(tenant_uuid=str(TOKEN_TENANT_UUID)),
                )
            ),
        )
