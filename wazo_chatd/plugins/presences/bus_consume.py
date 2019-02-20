# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.exceptions import UnknownUserException
from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import (
    Device,
    Line,
    Session,
    Tenant,
    User,
)
from .initiator import DEVICE_STATE_MAP, extract_device_name

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
        bus_consumer.on_event('line_device_associated', self._line_device_associated)
        bus_consumer.on_event('line_device_dissociated', self._line_device_dissociated)
        bus_consumer.on_event('DeviceStateChange', self._device_state_change)

    def _user_created(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            tenant = self._dao.tenant.find_or_create(tenant_uuid)
            logger.debug('Create user "%s"', user_uuid)
            user = User(uuid=user_uuid, tenant=tenant, state='unavailable')
            self._dao.user.create(user)

    def _user_deleted(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            logger.debug('Delete user "%s"', user_uuid)
            self._dao.user.delete(user)

    def _tenant_created(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Create tenant "%s"', tenant_uuid)
            tenant = Tenant(uuid=tenant_uuid)
            self._dao.tenant.create(tenant)

    def _tenant_deleted(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            tenant = self._dao.tenant.get(tenant_uuid)
            logger.debug('Delete tenant "%s"', tenant_uuid)
            self._dao.tenant.delete(tenant)

    def _session_created(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            try:
                user = self._dao.user.get([tenant_uuid], user_uuid)
            except UnknownUserException:
                logger.debug('Session "%s" has no valid user "%s"', session_uuid, user_uuid)
                return

            logger.debug('Create session "%s" for user "%s"', session_uuid, user_uuid)
            session = Session(uuid=session_uuid, user_uuid=user_uuid)
            self._dao.user.add_session(user, session)
            self._notifier.updated(user)

    def _session_deleted(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            try:
                user = self._dao.user.get([tenant_uuid], user_uuid)
            except UnknownUserException:
                logger.debug('Session "%s" has no valid user "%s"', session_uuid, user_uuid)
                return

            session = self._dao.session.get(session_uuid)
            logger.debug('Delete session "%s" for user "%s"', session_uuid, user_uuid)
            self._dao.user.remove_session(user, session)
            self._notifier.updated(user)

    def _line_associated(self, event):
        line_id = event['line_id']
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            logger.debug('Create line "%s"', line_id)
            line = Line(id=line_id)
            self._dao.user.add_line(user, line)
            self._notifier.updated(user)

    def _line_dissociated(self, event):
        line_id = event['line_id']
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            line = self._dao.line.get(line_id)
            logger.debug('Delete line "%s"', line_id)
            self._dao.user.remove_line(user, line)
            self._notifier.updated(user)

    def _line_device_associated(self, event):
        line_id = event['line']['id']
        device_name = extract_device_name(event['line'])
        with session_scope():
            line = self._dao.line.get(line_id)
            device = self._dao.device.find_by(name=device_name)
            if not device:
                device = self._dao.device.create(Device(name=device_name))
            logger.debug('Associate line "%s" with device "%s"', line_id, device_name)
            self._dao.line.associate_device(line, device)
            self._notifier.updated(line.user)

    def _line_device_dissociated(self, event):
        line_id = event['line']['id']
        device_name = extract_device_name(event['line'])
        with session_scope():
            line = self._dao.line.get(line_id)
            logger.debug('Dissociate line "%s" with device "%s"', line_id, device_name)
            self._dao.line.dissociate_device(line)
            self._notifier.updated(line.user)

    def _device_state_change(self, event):
        device_name = event['Device']
        state = DEVICE_STATE_MAP.get(event['State'], 'unavailable')
        with session_scope():
            device = self._dao.device.find_by(name=device_name)
            if not device:
                device = self._dao.device.create(Device(name=device_name))
            device.state = state
            logger.debug('Update device "%s" with state "%s"', device.name, device.state)
            self._dao.device.update(device)
            if device.line:
                self._notifier.updated(device.line.user)
