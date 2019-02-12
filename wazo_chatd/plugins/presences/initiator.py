# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.database.models import (
    User,
    Session,
    Tenant,
)
from wazo_chatd.database.helpers import session_scope
from wazo_chatd.exceptions import (
    UnknownSessionException,
    UnknownUserException,
)

logger = logging.getLogger(__name__)


class Initiator:

    def __init__(self, tenant_dao, user_dao, session_dao, auth):
        self._tenant_dao = tenant_dao
        self._user_dao = user_dao
        self._session_dao = session_dao
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
                try:
                    user = self._user_dao.get([tenant_uuid], uuid)
                except UnknownUserException:
                    logger.warning('Unknown user_uuid %s tenant_uuid %s' % (uuid, tenant_uuid))
                    continue
                self._user_dao.delete(user)

    def initiate_sessions(self):
        self._auth.set_token(self.token)
        sessions = self._auth.sessions.list(recurse=True)['items']

        sessions = set(
            (session['uuid'], session['user_uuid'], session['tenant_uuid'])
            for session in sessions
        )
        sessions_cached = set(
            (session.uuid, session.user_uuid, session.tenant_uuid)
            for session in self._session_dao.list_()
        )

        sessions_missing = sessions - sessions_cached
        with session_scope():
            for uuid, user_uuid, tenant_uuid in sessions_missing:
                logger.debug('Creating session with uuid: %s, user_uuid %s' % (uuid, user_uuid))
                try:
                    user = self._user_dao.get([tenant_uuid], user_uuid)
                except UnknownUserException:
                    logger.debug('Session has no valid user associated:' +
                                 'session_uuid %s, user_uuid %s' % uuid, user_uuid)
                    continue

                session = Session(uuid=uuid, user_uuid=user_uuid)
                self._user_dao.add_session(user, session)

        sessions_expired = sessions_cached - sessions
        with session_scope():
            for uuid, user_uuid, tenant_uuid in sessions_expired:
                logger.debug('Deleting session with uuid: %s, user_uuid %s' % (uuid, user_uuid))
                try:
                    user = self._user_dao.get([tenant_uuid], user_uuid)
                    session = self._session_dao.get(uuid)
                except (UnknownUserException, UnknownSessionException):
                    logger.warning('Unknown session or user: session_uuid %s, user_uuid %s' % (uuid, user_uuid))
                    continue

                self._user_dao.remove_session(user, session)
