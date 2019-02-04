# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.database.models import (
    User,
    Tenant,
)
from wazo_chatd.database.helpers import session_scope


class Initiator:

    def __init__(self, auth):
        self._auth = auth
        self._token = None

    @property
    def token(self):
        if not self._token:
            self._token = self._auth.token.new(expiration=120)['token']
        return self._token

    def initiate_tenants(self, tenant_dao):
        self._auth.set_token(self.token)
        tenants = self._auth.tenants.list()['items']

        tenants = set(tenant['uuid'] for tenant in tenants)
        tenants_cached = set(tenant.uuid for tenant in tenant_dao.list_())

        tenants_missing = tenants - tenants_cached
        with session_scope():
            for uuid in tenants_missing:
                tenant = Tenant(uuid=uuid)
                tenant_dao.create(tenant)

        tenants_expired = tenants_cached - tenants
        with session_scope():
            for uuid in tenants_expired:
                tenant = tenant_dao.get(uuid)
                tenant_dao.delete(tenant)

    def initiate_users(self, user_dao, confd):
        confd.set_token(self.token)
        users = confd.users.list(recurse=True)['items']

        users = set((user['uuid'], user['tenant_uuid']) for user in users)
        users_cached = set((u.uuid, u.tenant_uuid) for u in user_dao.list_(tenant_uuids=None))

        users_missing = users - users_cached
        with session_scope():
            for uuid, tenant_uuid in users_missing:
                user = User(uuid=uuid, tenant_uuid=tenant_uuid, state='unavailable')
                user_dao.create(user)

        users_expired = users_cached - users
        with session_scope():
            for uuid, tenant_uuid in users_expired:
                user = user_dao.get([tenant_uuid], uuid)
                user_dao.delete(user)
