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

    def __init__(self, tenant_dao, user_dao, session_dao, line_dao, notifier):
        self._tenant_dao = tenant_dao
        self._user_dao = user_dao
        self._session_dao = session_dao
        self._line_dao = line_dao
        self._notifier = notifier

    def subscribe(self, bus_consumer):
        bus_consumer.on_event('auth_tenant_created', self._tenant_created)
        bus_consumer.on_event('auth_tenant_deleted', self._tenant_deleted)
        bus_consumer.on_event('user_created', self._user_created)
        bus_consumer.on_event('user_deleted', self._user_deleted)
        bus_consumer.on_event('auth_session_created', self._session_created)
        bus_consumer.on_event('auth_session_deleted', self._session_deleted)
        bus_consumer.on_event('line_associated', self._line_associated)
        bus_consumer.on_event('line_dissociated', self._line_dissociated)
        # TODO listen on line_device association and dissociation to update line.device_name
        bus_consumer.on_event('DeviceStateChange', self._device_state_change)

    def _user_created(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            tenant = self._tenant_dao.find_or_create(tenant_uuid)
            logger.debug('Creating user with uuid: %s, tenant_uuid: %s', user_uuid, tenant_uuid)
            user = User(uuid=user_uuid, tenant=tenant, state='unavailable')
            self._user_dao.create(user)

    def _user_deleted(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Deleting user with uuid: %s, tenant_uuid: %s', user_uuid, tenant_uuid)
            user = self._user_dao.get([tenant_uuid], user_uuid)
            self._user_dao.delete(user)

    def _tenant_created(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Creating tenant with uuid: %s', tenant_uuid)
            tenant = Tenant(uuid=tenant_uuid)
            self._tenant_dao.create(tenant)

    def _tenant_deleted(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Deleting tenant with uuid: %s', tenant_uuid)
            tenant = self._tenant_dao.get(tenant_uuid)
            self._tenant_dao.delete(tenant)

    def _session_created(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            logger.debug('Creating session with uuid: %s, user_uuid: %s', session_uuid, user_uuid)
            user = self._user_dao.get([tenant_uuid], user_uuid)
            session = Session(uuid=session_uuid, user_uuid=user_uuid)
            self._user_dao.add_session(user, session)
            self._notifier.updated(user)

    def _session_deleted(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            logger.debug('Deleting session with uuid: %s, user_uuid: %s', session_uuid, user_uuid)
            user = self._user_dao.get([tenant_uuid], user_uuid)
            session = self._session_dao.get(session_uuid)
            self._user_dao.remove_session(user, session)
            self._notifier.updated(user)

    def _line_associated(self, event):
        line_id = event['line_id']
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Creating line with id: %s, user_uuid: %s' % (line_id, user_uuid))
            user = self._user_dao.get([tenant_uuid], user_uuid)
            line = Line(id=line_id, state='unavailable')
            self._user_dao.add_line(user, line)
            self._notifier.updated(user)

    def _line_dissociated(self, event):
        line_id = event['line_id']
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Deleting line with id: %s, user_uuid: %s' % (line_id, user_uuid))
            user = self._user_dao.get([tenant_uuid], user_uuid)
            line = self._line_dao.get(line_id)
            self._user_dao.remove_line(user, line)
            self._notifier.updated(user)

    def _device_state_change(self, event):
        device_name = event['Device']
        state = event['State']
        with session_scope():
            line = self._line_dao.get_by(device_name=device_name)
            logger.debug('Updating line with id: %s state: %s' % (line.id, state))
            line.state = DEVICE_STATE_MAP.get(state, 'unavailable')
            self._line_dao.update(line)
            self._notifier.updated(line.user)
