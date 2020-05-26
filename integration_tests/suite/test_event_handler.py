# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import random
import uuid

from hamcrest import (
    assert_that,
    contains,
    empty,
    has_entries,
    has_properties,
    has_items,
    not_,
)
from xivo_test_helpers import until

from wazo_chatd.database import models
from .helpers import fixtures
from .helpers.base import BaseIntegrationTest

USER_UUID_1 = uuid.uuid4()
ENDPOINT_NAME = 'PJSIP/name'


class TestEventHandler(BaseIntegrationTest):

    asset = 'base'

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
                    has_items(has_properties(uuid=user_uuid, tenant_uuid=tenant_uuid))
                ),
            )

        until.assert_(user_deleted, tries=3)

    @fixtures.db.user()
    def test_session_created(self, user):
        session_uuid = uuid.uuid4()
        user_uuid = user.uuid
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

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

        event = event_accumulator.accumulate()
        assert_that(
            event,
            contains(
                has_entries(
                    data=has_entries(
                        sessions=contains(
                            has_entries(uuid=str(session_uuid), mobile=True)
                        )
                    )
                )
            ),
        )

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.session(user_uuid=USER_UUID_1)
    def test_session_deleted(self, user, session):
        session_uuid = session.uuid
        user_uuid = user.uuid
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_session_deleted_event(session_uuid, user_uuid, user.tenant_uuid)

        def session_deleted():
            result = self._session.query(models.Session).all()
            assert_that(
                result,
                not_(has_items(has_properties(uuid=session_uuid, user_uuid=user_uuid))),
            )

        until.assert_(session_deleted, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(sessions=empty()))))

    @fixtures.db.user()
    def test_refresh_token_created(self, user):
        client_id = 'my-client-id'
        user_uuid = user.uuid
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

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

        event = event_accumulator.accumulate()
        assert_that(
            event, contains(has_entries(data=has_entries(mobile=True))),
        )

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.refresh_token(user_uuid=USER_UUID_1, mobile=True)
    def test_refresh_token_deleted(self, user, token):
        client_id = token.client_id
        user_uuid = user.uuid
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

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

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(mobile=False))))

    @fixtures.db.user()
    def test_user_line_associated(self, user):
        line_id = random.randint(1, 1000000)
        line_name = 'created-line'
        user_uuid = user.uuid
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

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
                        endpoint_name='PJSIP/{}'.format(line_name),
                    )
                ),
            )

        until.assert_(user_line_associated, tries=3)

        event = event_accumulator.accumulate()
        assert_that(
            event,
            contains(
                has_entries(
                    data=has_entries(
                        lines=contains(has_entries(id=line_id, state='unavailable'))
                    )
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
                        endpoint_name='PJSIP/{}'.format(line_name), state=endpoint_state
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
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_line_dissociated_event(line_id, user_uuid, user.tenant_uuid)

        def user_line_dissociated():
            result = self._session.query(models.Line).all()
            assert_that(
                result, not_(has_items(has_properties(id=line_id, user_uuid=user_uuid)))
            )

        until.assert_(user_line_dissociated, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(lines=empty()))))

    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='available')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    def test_device_state_changed(self, endpoint, user, line):
        line_id = line.id
        endpoint_name = endpoint.name
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_device_state_changed_event(endpoint_name, 'ONHOLD')

        def endpoint_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result, has_items(has_properties(name=endpoint_name, state='holding'))
            )

        until.assert_(endpoint_state_changed, tries=3)

        event = event_accumulator.accumulate()
        assert_that(
            event,
            contains(
                has_entries(
                    data=has_entries(
                        lines=contains(has_entries(id=line_id, state='holding'))
                    )
                )
            ),
        )

    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='available', channel_state='up')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    def test_device_state_change_inuse_when_channel_state_is_up(
        self, endpoint, user, line
    ):
        line_id = line.id
        endpoint_name = endpoint.name
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_device_state_changed_event(endpoint_name, 'INUSE')

        def endpoint_state_changed():
            event = event_accumulator.accumulate()
            assert_that(
                event,
                contains(
                    has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=line_id, state='talking'))
                        )
                    )
                ),
            )

        until.assert_(endpoint_state_changed, tries=3)

    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='talking', channel_state='down')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    def test_device_state_change_not_inuse_when_channel_state_is_down(
        self, endpoint, user, line
    ):
        line_id = line.id
        endpoint_name = endpoint.name
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_device_state_changed_event(endpoint_name, 'NOT_INUSE')

        def endpoint_state_changed():
            event = event_accumulator.accumulate()
            assert_that(
                event,
                contains(
                    has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=line_id, state='available'))
                        )
                    )
                ),
            )

        until.assert_(endpoint_state_changed, tries=3)

    def test_device_state_changed_create_endpoint(self):
        endpoint_name = 'missing-endpoint'

        self.bus.send_device_state_changed_event(endpoint_name, 'ONHOLD')

        def endpoint_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result, has_items(has_properties(name=endpoint_name, state='holding'))
            )

        until.assert_(endpoint_state_changed, tries=3)

    @fixtures.db.endpoint(name=ENDPOINT_NAME, channel_state='down')
    def test_new_channel(self, endpoint):
        endpoint_name = endpoint.name

        self.bus.send_new_channel_event(endpoint_name)

        def endpoint_channel_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result,
                has_items(has_properties(name=endpoint_name, channel_state='up')),
            )

        until.assert_(endpoint_channel_state_changed, tries=3)

    def test_new_channel_create_endpoint(self):
        endpoint_name = 'missing-endpoint'

        self.bus.send_new_channel_event(endpoint_name)

        def endpoint_channel_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result,
                has_items(has_properties(name=endpoint_name, channel_state='up')),
            )

        until.assert_(endpoint_channel_state_changed, tries=3)

    @fixtures.db.endpoint(name=ENDPOINT_NAME, channel_state='up')
    def test_hangup(self, endpoint):
        endpoint_name = endpoint.name

        self.bus.send_hangup_event(endpoint_name)

        def endpoint_channel_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result,
                has_items(has_properties(name=endpoint_name, channel_state='down')),
            )

        until.assert_(endpoint_channel_state_changed, tries=3)

    def test_hangup_create_endpoint(self):
        endpoint_name = 'missing-endpoint'

        self.bus.send_hangup_event(endpoint_name)

        def endpoint_channel_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Endpoint).all()
            assert_that(
                result,
                has_items(has_properties(name=endpoint_name, channel_state='down')),
            )

        until.assert_(endpoint_channel_state_changed, tries=3)

    @fixtures.db.endpoint(name=ENDPOINT_NAME, state='holding', channel_state='up')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, endpoint_name=ENDPOINT_NAME)
    def test_hangup_set_state_to_available_and_send_event(self, endpoint, user, line):
        line_id = line.id
        endpoint_name = endpoint.name
        routing_key = 'chatd.users.{uuid}.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_hangup_event(endpoint_name)

        def endpoint_state_changed():
            event = event_accumulator.accumulate()
            assert_that(
                event,
                contains(
                    has_entries(
                        data=has_entries(
                            lines=contains(has_entries(id=line_id, state='available'))
                        )
                    )
                ),
            )

        until.assert_(endpoint_state_changed, tries=3)
