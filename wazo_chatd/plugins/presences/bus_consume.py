# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import User, Session, Tenant

logger = logging.getLogger(__name__)


class BusEventHandler:

    def __init__(self, tenant_dao, user_dao, session_dao):
        self._tenant_dao = tenant_dao
        self._user_dao = user_dao
        self._session_dao = session_dao

    def subscribe(self, bus_consumer):
        bus_consumer.on_event('auth_tenant_created', self._tenant_created)
        bus_consumer.on_event('auth_tenant_deleted', self._tenant_deleted)
        bus_consumer.on_event('user_created', self._user_created)
        bus_consumer.on_event('user_deleted', self._user_deleted)
        bus_consumer.on_event('auth_session_created', self._session_created)
        bus_consumer.on_event('auth_session_deleted', self._session_deleted)

    def _user_created(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            tenant = self._tenant_dao.find_or_create(tenant_uuid)
            logger.debug('Creating user with uuid: %s, tenant_uuid: %s' % (user_uuid, tenant_uuid))
            user = User(uuid=user_uuid, tenant=tenant, state='unavailable')
            self._user_dao.create(user)

    def _user_deleted(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            logger.debug('Deleting user with uuid: %s, tenant_uuid: %s' % (user_uuid, tenant_uuid))
            user = self._user_dao.get([tenant_uuid], user_uuid)
            self._user_dao.delete(user)

    def _tenant_created(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Creating tenant with uuid: %s' % (tenant_uuid))
            tenant = Tenant(uuid=tenant_uuid)
            self._tenant_dao.create(tenant)

    def _tenant_deleted(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Deleting tenant with uuid: %s' % (tenant_uuid))
            tenant = self._tenant_dao.get(tenant_uuid)
            self._tenant_dao.delete(tenant)

    def _session_created(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            logger.debug('Creating session with uuid: %s, user_uuid: %s' % (session_uuid, user_uuid))
            user = self._user_dao.get([tenant_uuid], user_uuid)
            session = Session(uuid=session_uuid, user_uuid=user_uuid)
            self._user_dao.add_session(user, session)

    def _session_deleted(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            logger.debug('Deleting session with uuid: %s, user_uuid: %s' % (session_uuid, user_uuid))
            user = self._user_dao.get([tenant_uuid], user_uuid)
            session = self._session_dao.get(session_uuid)
            self._user_dao.remove_session(user, session)
