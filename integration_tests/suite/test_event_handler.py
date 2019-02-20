# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
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

USER_UUID_1 = str(uuid.uuid4())
DEVICE_NAME = 'PJSIP/name'


class TestEventHandler(BaseIntegrationTest):

    asset = 'base'

    def test_tenant_created(self):
        tenant_uuid = str(uuid.uuid4())
        self.bus.send_tenant_created_event(tenant_uuid)

        def tenant_created():
            result = self._dao.tenant.list_()
            assert_that(result, has_items(
                has_properties(uuid=tenant_uuid),
            ))

        until.assert_(tenant_created, tries=3)

    @fixtures.db.tenant()
    def test_tenant_deleted(self, tenant):
        tenant_uuid = tenant.uuid
        self.bus.send_tenant_deleted_event(tenant_uuid)

        def tenant_deleted():
            result = self._dao.tenant.list_()
            assert_that(result, not_(has_items(
                has_properties(uuid=tenant_uuid),
            )))

        until.assert_(tenant_deleted, tries=3)

    def test_user_created(self):
        user_uuid = str(uuid.uuid4())
        tenant_uuid = str(uuid.uuid4())
        self.bus.send_user_created_event(user_uuid, tenant_uuid)

        def user_created():
            result = self._dao.user.list_(tenant_uuids=None)
            assert_that(result, has_items(
                has_properties(uuid=user_uuid, tenant_uuid=tenant_uuid),
            ))

        until.assert_(user_created, tries=3)

    @fixtures.db.user()
    def test_user_deleted(self, user):
        user_uuid = user.uuid
        tenant_uuid = user.tenant_uuid
        self.bus.send_user_deleted_event(user_uuid, tenant_uuid)

        def user_deleted():
            result = self._dao.user.list_(tenant_uuids=None)
            assert_that(result, not_(has_items(
                has_properties(uuid=user_uuid, tenant_uuid=tenant_uuid),
            )))

        until.assert_(user_deleted, tries=3)

    @fixtures.db.user()
    def test_session_created(self, user):
        session_uuid = str(uuid.uuid4())
        user_uuid = user.uuid
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_session_created_event(session_uuid, user_uuid, user.tenant_uuid)

        def session_created():
            result = self._session.query(models.Session).all()
            assert_that(result, has_items(
                has_properties(uuid=session_uuid, user_uuid=user_uuid),
            ))

        until.assert_(session_created, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            sessions=contains(has_entries(uuid=session_uuid))
        ))))

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.session(user_uuid=USER_UUID_1)
    def test_session_deleted(self, user, session):
        session_uuid = session.uuid
        user_uuid = user.uuid
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_session_deleted_event(session_uuid, user_uuid, user.tenant_uuid)

        def session_deleted():
            result = self._session.query(models.Session).all()
            assert_that(result, not_(has_items(
                has_properties(uuid=session_uuid, user_uuid=user_uuid),
            )))

        until.assert_(session_deleted, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            sessions=empty()
        ))))

    @fixtures.db.user()
    def test_line_associated(self, user):
        line_id = random.randint(1, 1000000)
        user_uuid = user.uuid
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_line_associated_event(line_id, user_uuid, user.tenant_uuid)

        def line_associated():
            result = self._session.query(models.Line).all()
            assert_that(result, has_items(
                has_properties(id=line_id, user_uuid=user_uuid),
            ))

        until.assert_(line_associated, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            lines=contains(has_entries(id=line_id))
        ))))

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1)
    def test_line_dissociated(self, user, line):
        line_id = line.id
        user_uuid = user.uuid
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_line_dissociated_event(line_id, user_uuid, user.tenant_uuid)

        def line_dissociated():
            result = self._session.query(models.Line).all()
            assert_that(result, not_(has_items(
                has_properties(id=line_id, user_uuid=user_uuid),
            )))

        until.assert_(line_dissociated, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            lines=empty()
        ))))

    @fixtures.db.device(name=DEVICE_NAME, state='available')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, device_name=DEVICE_NAME)
    def test_device_state_changed(self, device, user, line):
        line_id = line.id
        device_name = device.name
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_device_state_changed_event(device_name, 'ONHOLD')

        def device_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Device).all()
            assert_that(result, has_items(
                has_properties(name=device_name, state='holding'),
            ))

        until.assert_(device_state_changed, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            lines=contains(has_entries(id=line_id, state='holding'))
        ))))

    def test_device_state_changed_create_device(self):
        device_name = 'missing-device'

        self.bus.send_device_state_changed_event(device_name, 'ONHOLD')

        def device_state_changed():
            self._session.expire_all()
            result = self._session.query(models.Device).all()
            assert_that(result, has_items(
                has_properties(name=device_name, state='holding'),
            ))

        until.assert_(device_state_changed, tries=3)

    @fixtures.db.device(state='available')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1)
    def test_line_device_associated(self, device, user, line):
        line_id = line.id
        line_name = device_name = device.name
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_line_device_associated_event(line_id, line_name)

        def line_device_associated():
            self._session.expire_all()
            result = self._session.query(models.Line).all()
            assert_that(result, has_items(
                has_properties(id=line_id, device_name=device_name),
            ))

        until.assert_(line_device_associated, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            lines=contains(has_entries(id=line_id, state='available'))
        ))))

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1)
    def test_line_device_associated_create_device(self, user, line):
        line_id = line.id
        line_name = device_name = 'missing-device'

        self.bus.send_line_device_associated_event(line_id, line_name)

        def line_device_associated():
            self._session.expire_all()
            result = self._session.query(models.Line).all()
            assert_that(result, has_items(
                has_properties(id=line_id, device_name=device_name),
            ))

        until.assert_(line_device_associated, tries=3)

    @fixtures.db.device(name=DEVICE_NAME, state='available')
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.line(user_uuid=USER_UUID_1, device_name=DEVICE_NAME)
    def test_line_device_dissociated(self, device, user, line):
        line_id = line.id
        routing_key = 'chatd.users.*.presences.updated'.format(uuid=user.uuid)
        event_accumulator = self.bus.accumulator(routing_key)

        self.bus.send_line_device_dissociated_event(line_id)

        def line_device_dissociated():
            self._session.expire_all()
            result = self._session.query(models.Line).all()
            assert_that(result, has_items(
                has_properties(id=line_id, device_name=None),
            ))

        until.assert_(line_device_dissociated, tries=3)

        event = event_accumulator.accumulate()
        assert_that(event, contains(has_entries(data=has_entries(
            lines=contains(has_entries(id=line_id, state='unavailable'))
        ))))
