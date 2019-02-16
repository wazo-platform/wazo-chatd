# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import (
    Line,
    Session,
    Tenant,
    User,
)
from .initiator import DEVICE_STATE_MAP

logger = logging.getLogger(__name__)


class BusEventHandler:

    def __init__(self, dao, notifier):
        self._dao = dao
        self._notifier = notifier

    def subscribe(self, bus_consumer):
        bus_consumer.on_event('auth_tenant_created', self._tenant_created)
        bus_consumer.on_event('auth_tenant_deleted', self._tenant_deleted)
        bus_consumer.on_event('user_created', self._user_created)
        bus_consumer.on_event('user_deleted', self._user_deleted)
        bus_consumer.on_event('auth_session_created', self._session_created)
        bus_consumer.on_event('auth_session_deleted', self._session_deleted)
        bus_consumer.on_event('line_associated', self._line_associated)  # user_line associated
        bus_consumer.on_event('line_dissociated', self._line_dissociated)  # user_line dissociated
        # TODO listen on line_device association and dissociation to update line.device_name
        bus_consumer.on_event('DeviceStateChange', self._device_state_change)

    def _user_created(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            tenant = self._dao.tenant.find_or_create(tenant_uuid)
            logger.debug('Creating user with uuid: %s, tenant_uuid: %s', user_uuid, tenant_uuid)
            user = User(uuid=user_uuid, tenant=tenant, state='unavailable')
            self._dao.user.create(user)

    def _user_deleted(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Deleting user with uuid: %s, tenant_uuid: %s', user_uuid, tenant_uuid)
            user = self._dao.user.get([tenant_uuid], user_uuid)
            self._dao.user.delete(user)

    def _tenant_created(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Creating tenant with uuid: %s', tenant_uuid)
            tenant = Tenant(uuid=tenant_uuid)
            self._dao.tenant.create(tenant)

    def _tenant_deleted(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Deleting tenant with uuid: %s', tenant_uuid)
            tenant = self._dao.tenant.get(tenant_uuid)
            self._dao.tenant.delete(tenant)

    def _session_created(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            logger.debug('Creating session with uuid: %s, user_uuid: %s', session_uuid, user_uuid)
            user = self._dao.user.get([tenant_uuid], user_uuid)
            session = Session(uuid=session_uuid, user_uuid=user_uuid)
            self._dao.user.add_session(user, session)
            self._notifier.updated(user)

    def _session_deleted(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            logger.debug('Deleting session with uuid: %s, user_uuid: %s', session_uuid, user_uuid)
            user = self._dao.user.get([tenant_uuid], user_uuid)
            session = self._dao.session.get(session_uuid)
            self._dao.user.remove_session(user, session)
            self._notifier.updated(user)

    def _line_associated(self, event):
        line_id = event['line_id']
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Creating line with id: %s, user_uuid: %s', line_id, user_uuid)
            user = self._dao.user.get([tenant_uuid], user_uuid)
            line = Line(id=line_id, state='unavailable')
            self._dao.user.add_line(user, line)
            self._notifier.updated(user)

    def _line_dissociated(self, event):
        line_id = event['line_id']
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Deleting line with id: %s, user_uuid: %s', line_id, user_uuid)
            user = self._dao.user.get([tenant_uuid], user_uuid)
            line = self._dao.line.get(line_id)
            self._dao.user.remove_line(user, line)
            self._notifier.updated(user)

    def _device_state_change(self, event):
        device_name = event['Device']
        state = event['State']
        with session_scope():
            line = self._dao.line.get_by(device_name=device_name)
            logger.debug('Updating line with id: %s state: %s', line.id, state)
            line.state = DEVICE_STATE_MAP.get(state, 'unavailable')
            self._dao.line.update(line)
            self._notifier.updated(line.user)
