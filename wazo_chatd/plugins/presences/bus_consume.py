# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import User

logger = logging.getLogger(__name__)


class BusEventHandler:

    def __init__(self, tenant_dao, user_dao):
        self._tenant_dao = tenant_dao
        self._user_dao = user_dao

    def subscribe(self, bus_consumer):
        bus_consumer.on_event('auth_tenant_created', self._tenant_created)
        bus_consumer.on_event('auth_tenant_deleted', self._tenant_deleted)
        bus_consumer.on_event('user_created', self._user_created)
        bus_consumer.on_event('user_deleted', self._user_deleted)

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
        pass

    def _tenant_deleted(self, event):
        pass
