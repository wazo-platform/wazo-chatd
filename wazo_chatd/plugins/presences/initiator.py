# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.database.models import (
    User,
    Tenant,
)
from wazo_chatd.database.helpers import session_scope

logger = logging.getLogger(__name__)


class Initiator:

    def __init__(self, tenant_dao, user_dao, auth):
        self._tenant_dao = tenant_dao
        self._user_dao = user_dao
        self._auth = auth
        self._token = None

    @property
    def token(self):
        if not self._token:
            self._token = self._auth.token.new(expiration=120)['token']
        return self._token

    def initiate_tenants(self):
        self._auth.set_token(self.token)
        tenants = self._auth.tenants.list()['items']

        tenants = set(tenant['uuid'] for tenant in tenants)
        tenants_cached = set(tenant.uuid for tenant in self._tenant_dao.list_())

        tenants_missing = tenants - tenants_cached
        with session_scope():
            for uuid in tenants_missing:
                logger.debug('Creating tenant with uuid: %s' % uuid)
                tenant = Tenant(uuid=uuid)
                self._tenant_dao.create(tenant)

        tenants_expired = tenants_cached - tenants
        with session_scope():
            for uuid in tenants_expired:
                logger.debug('Deleting tenant with uuid: %s' % uuid)
                tenant = self._tenant_dao.get(uuid)
                self._tenant_dao.delete(tenant)

    def initiate_users(self, confd):
        confd.set_token(self.token)
        users = confd.users.list(recurse=True)['items']

        users = set((user['uuid'], user['tenant_uuid']) for user in users)
        users_cached = set((u.uuid, u.tenant_uuid) for u in self._user_dao.list_(tenant_uuids=None))

        users_missing = users - users_cached
        with session_scope():
            for uuid, tenant_uuid in users_missing:
                # Avoid race condition between init tenant and init user
                tenant = self._tenant_dao.find_or_create(tenant_uuid)

                logger.debug('Creating user with uuid: %s' % uuid)
                user = User(uuid=uuid, tenant=tenant, state='unavailable')
                self._user_dao.create(user)

        users_expired = users_cached - users
        with session_scope():
            for uuid, tenant_uuid in users_expired:
                logger.debug('Deleting user with uuid: %s' % uuid)
                user = self._user_dao.get([tenant_uuid], uuid)
                self._user_dao.delete(user)
